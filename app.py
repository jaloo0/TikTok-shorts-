import streamlit as st
import requests
import base64
import time
import json


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

st.set_page_config(page_title="Master Shorts Pipeline Studio", page_icon="🎬", layout="wide")

st.title("🎬 Master Automated Shorts Pipeline Studio")
st.markdown("Full control center: GitHub Auto-Config, Recursive Repo File Editor, OpenRouter Free Models Integration, and Live Workflow Error Logger.")

# ==========================================
# 🔑 SIDEBAR: GITHUB & OPENROUTER CONFIG
# ==========================================
st.sidebar.header("⚙️ Credentials & API Config")

# GitHub Config
github_token = st.sidebar.text_input("GitHub PAT", type="password", help="Needs 'repo' scope")

if "owner" not in st.session_state:
    st.session_state.owner = ""
if "repos" not in st.session_state:
    st.session_state.repos = []
if "default_branch" not in st.session_state:
    st.session_state.default_branch = "main"

if github_token:
    gh_headers = {
        "Authorization": f"Bearer {github_token}",
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
if github_token and st.session_state.owner and selected_repo and selected_repo != "Enter token first...":
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
openrouter_key = st.sidebar.text_input("OpenRouter API Key", type="password", help="Used for clip selection and the code assistant.")
free_models = []
selected_openrouter_model = "none"
if openrouter_key:
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

st.sidebar.markdown("---")
st.sidebar.subheader("✨ Optional Gemini Config")
use_gemini = st.sidebar.checkbox("Enable Gemini for clip selection", value=False)
gemini_key = st.sidebar.text_input("Gemini API Key", type="password", help="Stored as an encrypted GitHub Actions repository secret when you run the workflow.")
gemini_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash"]
if gemini_key:
    try:
        gm_res = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": gemini_key}, timeout=20)
        if gm_res.status_code == 200:
            listed = gm_res.json().get("models", [])
            supported = [m["name"].removeprefix("models/") for m in listed if "generateContent" in m.get("supportedGenerationMethods", []) and m.get("name")]
            if supported: gemini_models = supported
        else:
            st.sidebar.caption("Could not load Gemini models; showing common model choices.")
    except Exception:
        st.sidebar.caption("Could not load Gemini models; showing common model choices.")
selected_gemini_model = st.sidebar.selectbox("Gemini Model", options=gemini_models)
if use_gemini and not gemini_key:
    st.sidebar.warning("Gemini is enabled, but its API key is missing.")

# ==========================================
# 📑 TABS: RUNNER, REPO EDITOR, OPENROUTER AI
# ==========================================
tab_run, tab_edit, tab_ai = st.tabs(["🚀 Run Pipeline & Error Logs", "📂 Repository File Editor", "💬 OpenRouter AI Assistant"])

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
        if not github_token or not st.session_state.owner or not selected_repo:
            st.error("Please configure GitHub credentials in the sidebar.")
        elif not video_url:
            st.error("Please provide a video URL.")
        else:
            gh_headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json"
            }
            dispatch_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/workflows/{workflow_file}/dispatches"
            payload = {
                "ref": st.session_state.default_branch,
                "inputs": {
                    "video_url": video_url,
                    "openrouter_model": selected_openrouter_model if use_ai_humor else "none",
                    "use_gemini": bool(use_gemini and gemini_key),
                    "gemini_model": selected_gemini_model
                }
            }
            
            try:
                # API keys are stored as encrypted repository secrets, never workflow inputs.
                if use_ai_humor and openrouter_key:
                    set_github_repo_secret(st.session_state.owner, selected_repo, "OPENROUTER_API_KEY", openrouter_key, gh_headers)
                if use_gemini and gemini_key:
                    set_github_repo_secret(st.session_state.owner, selected_repo, "GEMINI_API_KEY", gemini_key, gh_headers)
            except ImportError:
                st.error("Secure secret storage needs PyNaCl. Add PyNaCl>=1.5.0 to the app's own requirements and redeploy.")
                st.stop()
            except Exception as exc:
                st.error(f"Could not securely save API key as a GitHub Actions secret: {exc}")
                st.stop()
            with st.spinner("Dispatching pipeline..."):
                response = requests.post(dispatch_url, headers=gh_headers, json=payload, timeout=30)
                
            if response.status_code == 204:
                st.success("Pipeline triggered successfully! Monitoring execution...")
                
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
                    st.info(f"Monitoring Run ID: `{run_id}`")
                    status_placeholder = st.empty()
                    
                    while True:
                        time.sleep(5)
                        run_status_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/runs/{run_id}", headers=gh_headers).json()
                        status = run_status_res.get("status")
                        conclusion = run_status_res.get("conclusion")
                        
                        status_placeholder.markdown(f"**Status:** `{status}` | **Conclusion:** `{conclusion}`")
                        
                        if status == "completed":
                            if conclusion == "success":
                                st.success("🎉 Pipeline completed successfully!")
                                artifacts_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/runs/{run_id}/artifacts", headers=gh_headers).json()
                                artifacts = artifacts_res.get("artifacts", [])
                                if artifacts:
                                    download_url = artifacts[0]["archive_download_url"]
                                    st.markdown(f"📥 [Download Generated Short Artifact (.zip)]({download_url})")
                            else:
                                st.error(f"❌ Pipeline failed with conclusion: `{conclusion}`")
                                
                                # 🛑 AUTOMATIC WORKFLOW ERROR LOG FETCHER
                                st.subheader("📋 Workflow Error Logs & Diagnostics")
                                jobs_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/runs/{run_id}/jobs", headers=gh_headers)
                                if jobs_res.status_code == 200:
                                    jobs = jobs_res.json().get("jobs", [])
                                    for job in jobs:
                                        job_id = job.get("id")
                                        job_name = job.get("name")
                                        logs_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/jobs/{job_id}/logs", headers=gh_headers)
                                        if logs_res.status_code == 200:
                                            with st.expander(f"Logs for Job: {job_name}", expanded=True):
                                                st.code(logs_res.text[-5000:], language="log")
                        break
                else:
                    st.warning("Dispatched, but could not retrieve Run ID automatically.")
            else:
                st.error(f"Failed to dispatch: {response.status_code} - {response.text}")

# ------------------------------------------
# TAB 2: REPOSITORY FILE EDITOR
# ------------------------------------------
with tab_edit:
    st.subheader("Recursive Repository File Explorer & Editor")
    if not github_token or not st.session_state.owner or not selected_repo or selected_repo == "Enter token first...":
        st.warning("⚠️ Enter GitHub credentials in the sidebar first.")
    else:
        gh_headers = {
            "Authorization": f"Bearer {github_token}",
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
# TAB 3: OPENROUTER AI ASSISTANT & DIRECT PUSH EDITOR
# ------------------------------------------
with tab_ai:
    st.subheader("💬 OpenRouter AI Assistant & Direct Code Patter")
    st.markdown("Let OpenRouter AI modify your code line-by-line, review the changes, and commit/push directly to your repository.")
    
    if not github_token or not st.session_state.owner or not selected_repo or selected_repo == "Enter token first...":
        st.warning("⚠️ Please configure your GitHub credentials in the sidebar first.")
    else:
        gh_headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        # Fetch repository file tree for target file selection
        tree_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/git/trees/{st.session_state.default_branch}?recursive=1"
        tree_res = requests.get(tree_url, headers=gh_headers)
        
        if tree_res.status_code == 200:
            repo_files = [item["path"] for item in tree_res.json().get("tree", []) if item["type"] == "blob"]
            target_file = st.selectbox("Select Target File for AI Modification", options=repo_files, key="ai_target_file")
            
            file_content = ""
            file_sha = ""
            if target_file:
                file_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/{target_file}"
                file_res = requests.get(file_url, headers=gh_headers)
                if file_res.status_code == 200:
                    f_data = file_res.json()
                    file_sha = f_data["sha"]
                    try:
                        file_content = base64.b64decode(f_data["content"]).decode("utf-8")
                    except:
                        file_content = "[Binary file]"
            
            ai_prompt = st.text_area("🤖 AI Instructions / Bug Fix Request", placeholder="e.g., Fix the moviepy import error, update requirements, or optimize fetch_video...")
            
            # Initialize session state for AI-generated code preview
            if st.session_state.get("ai_generated_target") != target_file:
                st.session_state.ai_generated_target = target_file
                st.session_state.ai_generated_code = file_content
            
            if st.button("✨ Generate AI Code Modification", type="primary"):
                if not openrouter_key:
                    st.error("Please enter your OpenRouter API Key in the sidebar.")
                elif not ai_prompt:
                    st.error("Please enter instructions for the AI.")
                else:
                    headers = {
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json"
                    }
                    suffix = target_file.rsplit(".", 1)[-1].lower() if "." in target_file else ""
                    language = {"py":"Python", "js":"JavaScript", "jsx":"React JSX", "ts":"TypeScript", "tsx":"React TypeScript", "yml":"YAML", "yaml":"YAML", "json":"JSON", "html":"HTML", "css":"CSS", "md":"Markdown", "sh":"shell script"}.get(suffix, f"existing format ({suffix or 'unknown'})")
                    system_instruction = (
                        "You are a careful senior software engineer making a minimal, scoped edit. Modify ONLY the supplied target file and ONLY implement the requested feature. "
                        "Preserve unrelated code, names, formatting, configuration, and behavior. Never replace source code with a GitHub Actions workflow or YAML unless the target itself is .yml/.yaml and the request explicitly concerns that workflow. "
                        "Return the COMPLETE updated content of the one target file only, without explanations or diff markers."
                    )
                    user_payload = (
                        f"TARGET FILE: {target_file}\nRequired language/format: {language}\nRequested change: {ai_prompt}\n\n"
                        "Strict constraints: make the smallest correct change; do not output YAML for Python/JS/HTML; do not touch any other file.\n\n"
                        f"CURRENT FILE CONTENT:\n```{language}\n{file_content}\n```"
                    )
                    
                    body = {
                        "model": selected_openrouter_model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_payload}
                        ]
                    }
                    with st.spinner("AI is rewriting the code..."):
                        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
                        if res.status_code == 200:
                            raw_ans = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                            
                            # Clean up markdown code blocks if wrapped by the LLM
                            cleaned_code = raw_ans.strip()
                            if cleaned_code.startswith("```"):
                                lines = cleaned_code.splitlines()
                                if len(lines) > 2:
                                    if lines[-1].strip() == "```":
                                        lines = lines[1:-1]
                                    else:
                                        lines = lines[1:]
                                    cleaned_code = "\n".join(lines)
                            
                            suffix = target_file.rsplit(".", 1)[-1].lower() if "." in target_file else ""
                            if suffix == "py":
                                if cleaned_code.lstrip().startswith(("name:", "on:", "jobs:", "steps:")):
                                    st.error("Rejected AI output: this looks like workflow YAML, but the selected file is Python. Nothing was staged.")
                                else:
                                    try:
                                        compile(cleaned_code, target_file, "exec")
                                    except SyntaxError as syntax_error:
                                        st.error(f"Rejected invalid Python output: {syntax_error}. Nothing was staged.")
                                    else:
                                        st.session_state.ai_generated_code = cleaned_code
                                        st.success("Python update generated and syntax-checked. Review before committing.")
                                        st.rerun()
                            elif suffix in ("yml", "yaml") and not any(marker in cleaned_code for marker in ("jobs:", "steps:", "on:")):
                                st.error("Output does not look like a workflow YAML file. Nothing was staged.")
                            else:
                                st.session_state.ai_generated_code = cleaned_code
                                st.success("AI code generation complete! Review, tweak line-by-line below, and push when ready.")
                                st.rerun()
                        else:
                            st.error(f"OpenRouter API Error: {res.status_code} - {res.text}")
            
            # Interactive Review & Line-to-Line Code Editor Box
            st.markdown("---")
            st.markdown("### 📝 Code Review & Line-to-Line Editor")
            reviewed_code = st.text_area("Modify code line-by-line before committing:", value=st.session_state.ai_generated_code, height=450, key="reviewed_ai_code_box")
            
            commit_msg_ai = st.text_input("Commit Message", value=f"AI update to {target_file} via OpenRouter Studio")
            
            if st.button("🚀 Commit & Push AI Changes to GitHub", type="primary", key="push_ai_btn"):
                encoded_content = base64.b64encode(reviewed_code.encode("utf-8")).decode("utf-8")
                push_payload = {
                    "message": commit_msg_ai,
                    "content": encoded_content,
                    "sha": file_sha,
                    "branch": st.session_state.default_branch
                }
                file_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/{target_file}"
                commit_res = requests.put(file_url, headers=gh_headers, json=push_payload)
                if commit_res.status_code in [200, 201]:
                    st.success(f"Successfully committed and pushed `{target_file}` to GitHub!")
                else:
                    st.error(f"Commit failed: {commit_res.text}")
