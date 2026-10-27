import streamlit as st
import requests
import base64
import time

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
openrouter_key = st.sidebar.text_input("OpenRouter API Key", type="password", help="Get free model access via openrouter.ai")

# Auto-list free models from OpenRouter API
free_models = ["openai/gpt-4o-mini", "anthropic/claude-3-haiku"]
selected_openrouter_model = st.sidebar.selectbox("Select AI Model", options=["Enter OpenRouter Key..."])

if openrouter_key:
    try:
        or_res = requests.get("https://openrouter.ai/api/v1/models")
        if or_res.status_code == 200:
            all_models = or_res.json().get("data", [])
            # Filter free models where pricing prompt & completion are 0
            free_models = []
            for m in all_models:
                pricing = m.get("pricing", {})
                p_prompt = float(pricing.get("prompt", 1))
                p_compl = float(pricing.get("completion", 1))
                if p_prompt == 0.0 and p_compl == 0.0:
                    free_models.append(m.get("id"))
            if not free_models:
                free_models = [m.get("id") for m in all_models[:10]] # fallback
            selected_openrouter_model = st.sidebar.selectbox("Select Free OpenRouter Model", options=free_models)
        else:
            st.sidebar.error("Failed to fetch OpenRouter models.")
    except Exception as e:
        st.sidebar.error(f"OpenRouter error: {e}")

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
                    "openrouter_model": selected_openrouter_model if use_ai_humor else "none"
                }
            }
            
            with st.spinner("Dispatching pipeline..."):
                response = requests.post(dispatch_url, headers=gh_headers, json=payload)
                
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
            if "ai_generated_code" not in st.session_state:
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
                    system_instruction = (
                        "You are an expert software engineer. The user wants you to modify the provided source code "
                        "based on their instructions. Return ONLY the complete updated file content in raw text or wrapped in a standard code block. "
                        "Do not include conversational filler before or after the code so it can be parsed cleanly."
                    )
                    user_payload = f"File Path: {target_file}\n\nCurrent Content:\n```\n{file_content}\n```\n\nInstructions: {ai_prompt}"
                    
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