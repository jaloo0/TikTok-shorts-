import streamlit as st
import requests
import base64
import time

st.set_page_config(page_title="Shorts Pipeline Studio", page_icon="🎬", layout="wide")

st.title("🎬 Automated Shorts Pipeline Studio")
st.markdown("Auto-configure your GitHub credentials, browse and edit your **entire repository tree**, run pipelines live, and stream logs.")

# ==========================================
# 🔑 SIDEBAR: AUTO-CONFIG CREDENTIALS & BRANCH
# ==========================================
st.sidebar.header("⚙️ GitHub Auto-Config")
github_token = st.sidebar.text_input("GitHub Personal Access Token (PAT)", type="password", help="Needs 'repo' scope")

# Initialize session state
if "owner" not in st.session_state:
    st.session_state.owner = ""
if "repos" not in st.session_state:
    st.session_state.repos = []
if "default_branch" not in st.session_state:
    st.session_state.default_branch = "main"

# Auto-detect user and repositories if token is provided
if github_token:
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        user_res = requests.get("https://api.github.com/user", headers=headers)
        if user_res.status_code == 200:
            user_data = user_res.json()
            st.session_state.owner = user_data.get("login")
            st.sidebar.success(f"Connected: **{st.session_state.owner}**")
            
            # Fetch user repositories
            repos_res = requests.get(f"https://api.github.com/users/{st.session_state.owner}/repos?per_page=100", headers=headers)
            if repos_res.status_code == 200:
                st.session_state.repos = [repo["name"] for repo in repos_res.json()]
        else:
            st.sidebar.error("Invalid GitHub Token. Check permissions.")
    except Exception as e:
        st.sidebar.error(f"Connection error: {e}")

# Repo selection dropdown (Auto-corrects manual typos)
selected_repo = st.sidebar.selectbox("Select Repository", options=st.session_state.repos if st.session_state.repos else ["Enter token first..."])

# Auto-detect default branch & workflow files if repo is selected
workflow_file = "video_pipeline.yml"
if github_token and st.session_state.owner and selected_repo and selected_repo != "Enter token first...":
    repo_info_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}", headers=headers)
    if repo_info_res.status_code == 200:
        st.session_state.default_branch = repo_info_res.json().get("default_branch", "main")
        st.sidebar.info(f"Branch: `{st.session_state.default_branch}`")
        
    # Find workflow files in repo
    wf_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/.github/workflows"
    wf_res = requests.get(wf_url, headers=headers)
    if wf_res.status_code == 200:
        workflows = [f["name"] for f in wf_res.json() if f["name"].endswith((".yml", ".yaml"))]
        if workflows:
            workflow_file = st.sidebar.selectbox("Select Workflow", options=workflows)

# ==========================================
# 📑 TABS: PIPELINE RUNNER vs FULL REPO EDITOR
# ==========================================
tab_run, tab_edit = st.tabs(["🚀 Run Pipeline & Logs", "📂 Full Repository File Explorer & Editor"])

# ------------------------------------------
# TAB 1: RUN PIPELINE & LIVE MONITORING
# ------------------------------------------
with tab_run:
    st.subheader("Trigger & Monitor Pipeline Execution")
    video_url = st.text_input("🔗 Enter Source Video URL", placeholder="https://www.youtube.com/watch?v=...")

    if st.button("🚀 Run Pipeline on GitHub Actions", type="primary"):
        if not github_token or not st.session_state.owner or not selected_repo:
            st.error("Please provide a valid GitHub Token and select a repository in the sidebar.")
        elif not video_url:
            st.error("Please enter a target video URL.")
        else:
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json"
            }
            dispatch_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/workflows/{workflow_file}/dispatches"
            payload = {
                "ref": st.session_state.default_branch,
                "inputs": {"video_url": video_url}
            }
            
            with st.spinner("Dispatching pipeline job via GitHub API..."):
                response = requests.post(dispatch_url, headers=headers, json=payload)
                
            if response.status_code == 204:
                st.success("Pipeline triggered successfully! Waiting for runner...")
                
                runs_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/workflows/{workflow_file}/runs?per_page=1"
                run_id = None
                for _ in range(10):
                    time.sleep(3)
                    runs_res = requests.get(runs_url, headers=headers).json()
                    runs = runs_res.get("workflow_runs", [])
                    if runs:
                        run_id = runs[0]["id"]
                        break
                
                if run_id:
                    st.info(f"Monitoring GitHub Actions Run ID: `{run_id}`")
                    status_placeholder = st.empty()
                    
                    while True:
                        time.sleep(5)
                        run_status_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/runs/{run_id}", headers=headers).json()
                        status = run_status_res.get("status")
                        conclusion = run_status_res.get("conclusion")
                        
                        status_placeholder.markdown(f"**Status:** `{status}` | **Conclusion:** `{conclusion}`")
                        
                        if status == "completed":
                            if conclusion == "success":
                                st.success("🎉 Pipeline completed successfully!")
                                artifacts_res = requests.get(f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/actions/runs/{run_id}/artifacts", headers=headers).json()
                                artifacts = artifacts_res.get("artifacts", [])
                                if artifacts:
                                    download_url = artifacts[0]["archive_download_url"]
                                    st.markdown(f"📥 [Download Generated Short Artifact (.zip)]({download_url}) *(Requires GitHub login)*")
                            else:
                                st.error(f"Pipeline failed with conclusion: {conclusion}")
                            break
                else:
                    st.warning("Workflow dispatched, but could not auto-retrieve Run ID. Check your GitHub Actions tab.")
            else:
                st.error(f"Failed to trigger workflow: {response.status_code} - {response.text}")

# ------------------------------------------
# TAB 2: FULL REPO EXPLORER & FILE EDITOR
# ------------------------------------------
with tab_edit:
    st.subheader("Full Repository File Explorer & Editor")
    st.markdown("Recursively fetches all folders and files in your repository so you can inspect, modify, and commit any code file instantly.")

    if not github_token or not st.session_state.owner or not selected_repo or selected_repo == "Enter token first...":
        st.warning("⚠️ Please enter your GitHub Token and select a repository in the sidebar first.")
    else:
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        # Recursively fetch entire repository tree using Git Trees API
        tree_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/git/trees/{st.session_state.default_branch}?recursive=1"
        tree_res = requests.get(tree_url, headers=headers)
        
        if tree_res.status_code == 200:
            tree_data = tree_res.json()
            # Filter for files (blobs) only
            repo_files = [item["path"] for item in tree_data.get("tree", []) if item["type"] == "blob"]
            
            if repo_files:
                selected_file = st.selectbox("Select Any File in Repository", options=repo_files)
                
                if selected_file:
                    file_url = f"https://api.github.com/repos/{st.session_state.owner}/{selected_repo}/contents/{selected_file}"
                    file_res = requests.get(file_url, headers=headers)
                    
                    if file_res.status_code == 200:
                        file_data = file_res.json()
                        file_sha = file_data["sha"]
                        
                        try:
                            file_content_decoded = base64.b64decode(file_data["content"]).decode("utf-8")
                        except Exception:
                            file_content_decoded = "[Binary file or unable to decode as UTF-8 text]"
                        
                        # Determine appropriate height based on content
                        editor_height = max(350, min(600, len(file_content_decoded.splitlines()) * 20))
                        
                        edited_code = st.text_area(f"Editing: `{selected_file}`", value=file_content_decoded, height=editor_height)
                        commit_message = st.text_input("Commit Message", value=f"Update {selected_file} via Streamlit Studio")
                        
                        if st.button("💾 Commit Changes to GitHub", type="primary"):
                            encoded_content = base64.b64encode(edited_code.encode("utf-8")).decode("utf-8")
                            commit_payload = {
                                "message": commit_message,
                                "content": encoded_content,
                                "sha": file_sha,
                                "branch": st.session_state.default_branch
                            }
                            
                            commit_res = requests.put(file_url, headers=headers, json=commit_payload)
                            if commit_res.status_code in [200, 201]:
                                st.success(f"Successfully committed changes to `{selected_file}` on branch `{st.session_state.default_branch}`!")
                            else:
                                st.error(f"Commit failed: {commit_res.status_code} - {commit_res.text}")
                    else:
                        st.error("Could not fetch file content.")
            else:
                st.warning("No files found in this repository branch.")
        else:
            st.error(f"Could not fetch repository tree: {tree_res.status_code} - {tree_res.text}")
