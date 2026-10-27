import streamlit as st
import requests
import base64
import time
import json

st.set_page_config(page_title="Master Shorts Pipeline Studio", page_icon="🎬", layout="wide")

st.title("🎬 Master Automated Shorts Pipeline Studio")
st.markdown("Full control center: GitHub Auto-Config, Recursive Repo File Editor, OpenRouter Free Models Integration, and Live Workflow Error Logger.")

# ==========================================
# 🔑 INITIALIZE SESSION STATE
# ==========================================
if "github_token" not in st.session_state:
    st.session_state.github_token = ""
if "openrouter_key" not in st.session_state:
    st.session_state.openrouter_key = ""
if "owner" not in st.session_state:
    st.session_state.owner = ""
if "repos" not in st.session_state:
    st.session_state.repos = []
if "default_branch" not in st.session_state:
    st.session_state.default_branch = "main"
if "active_run_id" not in st.session_state:
    st.session_state.active_run_id = None
if "ai_modified_files" not in st.session_state:
    st.session_state.ai_modified_files = {} # Stores {filepath: {"content": ..., "sha": ...}}

def set_github_repo_secret(owner, repo, secret_name, secret_value, headers):
    """Store a key as an encrypted GitHub Actions repository secret."""
    from nacl.public import PublicKey, SealedBox
    from nacl.encoding import Base64Encoder
    base = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets"
    key_res = requests.get(f"{base}/public-key", headers=headers, timeout=20)
    key_res.raise_for_status()
    public_data = key_res.json()
    public_key = PublicKey(public_data["key"].encode(), Base64Encoder)
    encrypted = SealedBox(public_key).encrypt(secret_value.encode())
    import base64 as _base64
    saved = requests.put(f"{base}/{secret_name}", headers=headers, json={
        "encrypted_value": _base64.b64encode(encrypted).decode(), "key_id": public_data["key_id"]
    }, timeout=20)
    saved.raise_for_status()
    return saved.status_code in (201, 204)

# ==========================================
# ⚙️ SIDEBAR: GITHUB & OPENROUTER CONFIG
# ==========================================
st.sidebar.header("⚙️ Credentials & API Config")

github_token = st.sidebar.text_input("GitHub PAT", value=st.session_state.github_token, type="password", help="Needs 'repo' scope", key="gh_token_input")
if github_token != st.session_state.github_token:
    st.session_state.github_token = github_token

if st.session_state.github_token:
    gh_headers = {
        "Authorization": f"Bearer {st.session_state.github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        user_res = requests.get("https://api.github.com/user", headers=gh_headers)
        if user_res.status_code == 200:
            user_data = user_res.json()
            st.session_state.owner = user_data.get("login")
            st.sidebar.success(f"GitHub Connected: **{st.session_state.owner}**")
            
            repos_res = requests.get(f"https://api.github.com/users/{st.session_state.owner}/repos?per_page=100", headers=gh_headers)
            if repos_res.status_code == 200:
                st.session_state.repos = [repo["name"] for repo in repos_res.json()]
    except Exception as e:
        st.sidebar.error(f"GH connection error: {e}")

selected_repo = st.sidebar.selectbox("Select Repository", options=st.session_state.repos if st.session_state.repos else ["Enter token first..."])

workflow_file = "video_pipeline.yml"
if st.session_state.github_token and st.session_state.owner and selected_repo and selected_repo != "Enter token first...":
    repo_info_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}", headers=gh_headers)
    if repo_info_res.status_code == 200:
        st.session_state.default_branch = repo_info_res.json().get("default_branch", "main")
        
    wf_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/.github/workflows"
    wf_res = requests.get(wf_url, headers=gh_headers)
    if wf_res.status_code == 200:
        workflows = [f["name"] for f in wf_res.json() if f["name"].endswith((".yml", ".yaml"))]
        if workflows:
            workflow_file = st.sidebar.selectbox("Select Workflow", options=workflows)

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 OpenRouter AI Config")
openrouter_key = st.sidebar.text_input("OpenRouter API Key", value=st.session_state.openrouter_key, type="password", help="Used for clip selection and code assistant.", key="or_key_input")
if openrouter_key != st.session_state.openrouter_key:
    st.session_state.openrouter_key = openrouter_key

free_models = []
selected_openrouter_model = "none"
if st.session_state.openrouter_key:
    try:
        or_res = requests.get("https://openrouter.ai/api/v1/models", timeout=20)
        or_res.raise_for_status()
        all_models = or_res.json().get("data", [])
        free_models = [m.get("id") for m in all_models if m.get("id") and float(m.get("pricing", {}).get("prompt", 1) or 1) == 0 and float(m.get("pricing", {}).get("completion", 1) or 1) == 0]
        if not free_models:
            free_models = [m.get("id") for m in all_models if m.get("id")][:30]
        if free_models:
            selected_openrouter_model = st.sidebar.selectbox("Select OpenRouter Model", options=free_models, key="openrouter_model_select")
        else:
            st.sidebar.warning("No models returned by OpenRouter.")
    except Exception as exc:
        st.sidebar.error(f"OpenRouter model lookup failed: {exc}")
else:
    st.sidebar.caption("Enter an OpenRouter key to load available models.")

# ==========================================
# 📑 TABS: RUNNER, REPO EDITOR, OPENROUTER AI
# ==========================================
tab_run, tab_edit, tab_ai = st.tabs(["🚀 Run Pipeline & Error Logs", "📂 Repository File Editor", "💬 Autonomous OpenRouter AI"])

# ------------------------------------------
# TAB 1: RUN PIPELINE & LIVE ERROR LOGS
# ------------------------------------------
with tab_run:
    st.subheader("Trigger Pipeline & Stream Logs / Errors")
    video_url = st.text_input("🔗 Enter Source Video URL", placeholder="https://www.youtube.com/watch?v=...")
    
    col1, col2 = st.columns(2)
    with col1:
        use_ai_humor = st.checkbox("Enable OpenRouter AI Humor/Transcript Analysis", value=True)
    with col2:
        st.markdown(f"**Active AI Model:** `{selected_openrouter_model}`")

    if st.button("🚀 Run Pipeline on GitHub Actions", type="primary"):
        if not st.session_state.github_token or not st.session_state.owner or not selected_repo:
            st.error("Please configure GitHub credentials in the sidebar.")
        elif not video_url:
            st.error("Please provide a video URL.")
        else:
            gh_headers = {
                "Authorization": f"Bearer {st.session_state.github_token}",
                "Accept": "application/vnd.github+json"
            }
            dispatch_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/workflows/{workflow_file}/dispatches"
            payload = {
                "ref": st.session_state.default_branch,
                "inputs": {
                    "video_url": video_url,
                    "openrouter_model": selected_openrouter_model if use_ai_humor else "none",
                    "use_gemini": False,
                    "gemini_model": "none"
                }
            }
            
            try:
                if use_ai_humor and st.session_state.openrouter_key:
                    set_github_repo_secret(st.session_state.owner, selected_repo, "OPENROUTER_API_KEY", st.session_state.openrouter_key, gh_headers)
            except Exception as exc:
                st.error(f"Could not securely save API key as a GitHub Actions secret: {exc}")
                st.stop()

            with st.spinner("Dispatching pipeline..."):
                response = requests.post(dispatch_url, headers=gh_headers, json=payload, timeout=30)
                
            if response.status_code == 204:
                st.success("Pipeline triggered successfully! Locating Run ID...")
                runs_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/workflows/{workflow_file}/runs?per_page=1"
                run_id = None
                for _ in range(10):
                    time.sleep(3)
                    runs_res = requests.get(runs_url, headers=gh_headers).json()
                    runs = runs_res.get("workflow_runs", [])
                    if runs:
                        run_id = runs[0]["id"]
                        break
                
                if run_id:
                    st.session_state.active_run_id = run_id
                    st.rerun()
                else:
                    st.warning("Dispatched, but could not retrieve Run ID automatically.")
            else:
                st.error(f"Failed to dispatch: {response.status_code} - {response.text}")

    if st.session_state.active_run_id:
        st.markdown("---")
        st.subheader(f"🔄 Active Pipeline Monitoring (Run ID: `{st.session_state.active_run_id}`)")
        gh_headers = {
            "Authorization": f"Bearer {st.session_state.github_token}",
            "Accept": "application/vnd.github+json"
        }
        run_status_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/runs/{st.session_state.active_run_id}", headers=gh_headers)
        if run_status_res.status_code == 200:
            run_data = run_status_res.json()
            status = run_data.get("status")
            conclusion = run_data.get("conclusion")
            st.markdown(f"**Status:** `{status}` | **Conclusion:** `{conclusion}`")
            if status == "completed":
                if conclusion == "success":
                    st.success("🎉 Pipeline completed successfully!")
                else:
                    st.error(f"❌ Pipeline failed with conclusion: `{conclusion}`")
                if st.button("Clear Finished Run Monitor"):
                    st.session_state.active_run_id = None
                    st.rerun()
            else:
                if st.button("🔄 Refresh Run Status"):
                    st.rerun()

# ------------------------------------------
# TAB 2: REPOSITORY FILE EDITOR
# ------------------------------------------
with tab_edit:
    st.subheader("Recursive Repository File Explorer & Editor")
    if not st.session_state.github_token or not st.session_state.owner or not selected_repo or selected_repo == "Enter token first...":
        st.warning("⚠️ Enter GitHub credentials in the sidebar first.")
    else:
        gh_headers = {
            "Authorization": f"Bearer {st.session_state.github_token}",
            "Accept": "application/vnd.github+json"
        }
        tree_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/git/trees/{st.session_state.default_branch}?recursive=1"
        tree_res = requests.get(tree_url, headers=gh_headers)
        
        if tree_res.status_code == 200:
            repo_files = [item["path"] for item in tree_res.json().get("tree", []) if item["type"] == "blob"]
            selected_file = st.selectbox("Select File to Edit", options=repo_files)
            
            if selected_file:
                file_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/{selected_file}"
                file_res = requests.get(file_url, headers=gh_headers)
                
                if file_res.status_code == 200:
                    file_data = file_res.json()
                    file_sha = file_data["sha"]
                    try:
                        content = base64.b64decode(file_data["content"]).decode("utf-8")
                    except:
                        content = "[Binary file]"
                        
                    edited_code = st.text_area(f"Editing: `{selected_file}`", value=content, height=450)
                    commit_msg = st.text_input("Commit Message", value=f"Update {selected_file} via Master Studio")
                    
                    if st.button("💾 Commit & Push to GitHub", type="primary"):
                        encoded = base64.b64encode(edited_code.encode("utf-8")).decode("utf-8")
                        payload = {
                            "message": commit_msg,
                            "content": encoded,
                            "sha": file_sha,
                            "branch": st.session_state.default_branch
                        }
                        commit_res = requests.put(file_url, headers=gh_headers, json=payload)
                        if commit_res.status_code in [200, 201]:
                            st.success(f"Successfully committed `{selected_file}`!")
                        else:
                            st.error(f"Commit failed: {commit_res.text}")

# ------------------------------------------
# TAB 3: AUTONOMOUS OPENROUTER AI ASSISTANT
# ------------------------------------------
with tab_ai:
    st.subheader("💬 Autonomous OpenRouter AI Assistant")
    st.markdown("Describe the feature or bug fix you want. The AI will independently inspect your codebase, modify one or multiple files, and load them into the review window below.")
    
    if not st.session_state.github_token or not st.session_state.owner or not selected_repo or selected_repo == "Enter token first...":
        st.warning("⚠️ Please configure your GitHub credentials in the sidebar first.")
    else:
        gh_headers = {
            "Authorization": f"Bearer {st.session_state.github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        ai_prompt = st.text_area("🤖 What would you like to build, fix, or update?", placeholder="e.g., Add error handling to video fetching, update requirements, and add a clean logger function across files...")
        
        if st.button("✨ Let AI Analyze & Write Code", type="primary"):
            if not st.session_state.openrouter_key:
                st.error("Please enter your OpenRouter API Key in the sidebar.")
            elif not ai_prompt:
                st.error("Please enter your instructions for the AI.")
            else:
                with st.spinner("AI is analyzing repository files and writing code..."):
                    # 1. Fetch entire file tree and ignore heavy/system folders
                    tree_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/git/trees/{st.session_state.default_branch}?recursive=1"
                    tree_res = requests.get(tree_url, headers=gh_headers)
                    
                    ignored_prefixes = (
                        "node_modules/", ".git/", ".vscode/", ".idea/", "helm-charts/", 
                        "tests/", "coverage", "Dockerfile", "docker-compose", ".dockerignore", 
                        ".gitignore", "LICENSE", "README.md", ".env", ".editorconfig", "Makefile"
                    )
                    
                    codebase_context = {}
                    if tree_res.status_code == 200:
                        all_items = tree_res.json().get("tree", [])
                        for item in all_items:
                            if item["type"] == "blob":
                                path = item["path"]
                                # Filter out excluded patterns
                                if any(path.startswith(prefix) or path == prefix.strip("*") for prefix in ignored_prefixes):
                                    continue
                                
                                # Fetch file content & sha
                                f_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/{path}"
                                f_res = requests.get(f_url, headers=gh_headers)
                                if f_res.status_code == 200:
                                    f_json = f_res.json()
                                    try:
                                        decoded = base64.b64decode(f_json["content"]).decode("utf-8")
                                        codebase_context[path] = {
                                            "content": decoded,
                                            "sha": f_json.get("sha", "")
                                        }
                                    except Exception:
                                        pass # Skip binary files

                    # 2. Construct AI Prompt with repository context
                    system_instruction = (
                        "You are an autonomous senior software engineer. The user will give you a task. "
                        "Examine the provided repository files, determine which one or more files need to be created or modified, "
                        "and output your solution strictly as a JSON object where each key is the relative file path and the value is the complete updated file content string. "
                        "Example format:\n{\n  \"pipeline.py\": \"import os...\",\n  \"requirements.txt\": \"yt-dlp\\n...\"\n}\n"
                        "Return ONLY valid JSON containing the modified or new files. Do not include markdown chat outside the JSON structure."
                    )
                    
                    user_payload = f"User Request: {ai_prompt}\n\nRepository Files Context:\n{json.dumps(codebase_context, indent=2)}"
                    
                    headers = {
                        "Authorization": f"Bearer {st.session_state.openrouter_key}",
                        "Content-Type": "application/json"
                    }
                    body = {
                        "model": selected_openrouter_model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_payload}
                        ]
                    }
                    
                    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=60)
                    if res.status_code == 200:
                        raw_ans = res.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        
                        # Clean markdown code blocks if present
                        if raw_ans.startswith("```"):
                            lines = raw_ans.splitlines()
                            if len(lines) > 2:
                                if lines[-1].strip() == "```":
                                    lines = lines[1:-1]
                                else:
                                    lines = lines[1:]
                                raw_ans = "\n".join(lines)
                        
                        try:
                            parsed_files = json.loads(raw_ans)
                            if isinstance(parsed_files, dict):
                                st.session_state.ai_modified_files = {}
                                for fpath, fcontent in parsed_files.items():
                                    existing_sha = codebase_context.get(fpath, {}).get("sha", "")
                                    st.session_state.ai_modified_files[fpath] = {
                                        "content": fcontent,
                                        "sha": existing_sha
                                    }
                                st.success(f"AI successfully updated/created {len(parsed_files)} file(s). Review them below!")
                                st.rerun()
                            else:
                                st.error("AI response JSON format was invalid. Please try again.")
                        except json.JSONDecodeError:
                            st.error(f"Failed to parse AI JSON output:\n{raw_ans}")
                    else:
                        st.error(f"OpenRouter API Error: {res.status_code} - {res.text}")

        # 3. Multi-File Code Review & Push Window
        if st.session_state.ai_modified_files:
            st.markdown("---")
            st.subheader("📝 Multi-File AI Code Review & Editor")
            
            file_choices = list(st.session_state.ai_modified_files.keys())
            selected_review_file = st.selectbox("Select Modified File to Review", options=file_choices, key="review_file_select")
            
            if selected_review_file:
                file_info = st.session_state.ai_modified_files[selected_review_file]
                
                reviewed_code = st.text_area(
                    f"Editing line-by-line: `{selected_review_file}`", 
                    value=file_info["content"], 
                    height=400, 
                    key=f"text_area_{selected_review_file}"
                )
                
                # Update session state live as user edits
                st.session_state.ai_modified_files[selected_review_file]["content"] = reviewed_code
                
                commit_msg_ai = st.text_input("Commit Message for this file", value=f"AI update to {selected_review_file} via Autonomous Studio", key=f"commit_msg_{selected_review_file}")
                
                if st.button(f"🚀 Commit & Push `{selected_review_file}` to GitHub", type="primary", key=f"push_btn_{selected_review_file}"):
                    encoded_content = base64.b64encode(reviewed_code.encode("utf-8")).decode("utf-8")
                    push_payload = {
                        "message": commit_msg_ai,
                        "content": encoded_content,
                        "branch": st.session_state.default_branch
                    }
                    if file_info["sha"]:
                        push_payload["sha"] = file_info["sha"]
                        
                    file_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/{selected_review_file}"
                    commit_res = requests.put(file_url, headers=gh_headers, json=push_payload)
                    
                    if commit_res.status_code in [200, 201]:
                        st.success(f"Successfully committed and pushed `{selected_review_file}`!")
                        # Update stored SHA for subsequent edits
                        new_data = commit_res.json()
                        if "content" in new_data and "sha" in new_data["content"]:
                            st.session_state.ai_modified_files[selected_review_file]["sha"] = new_data["content"]["sha"]
                    else:
                        st.error(f"Commit failed: {commit_res.text}")