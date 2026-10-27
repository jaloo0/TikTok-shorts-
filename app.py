import streamlit as st
import requests
import time
import os

st.set_page_config(page_title="Shorts Pipeline Dashboard", page_icon="🎬", layout="centered")

st.title("🎬 Automated Shorts Pipeline")
st.markdown("Trigger cloud video processing on **GitHub Actions** for free, view live logs, and preview your generated Shorts.")

# Sidebar Configuration for GitHub Credentials
st.sidebar.header("⚙️ GitHub Configuration")
GITHUB_TOKEN = st.sidebar.text_input("GitHub Personal Access Token (PAT)", type="password", help="Needs 'repo' or 'actions:write' scope")
REPO_OWNER = st.sidebar.text_input("GitHub Username / Owner", placeholder="e.g. johndoe")
REPO_NAME = st.sidebar.text_input("Repository Name", placeholder="e.g. my-short-pipeline")
WORKFLOW_FILE = st.sidebar.text_input("Workflow Filename", value="video_pipeline.yml")

# Main Interface
video_url = st.text_input("🔗 Enter Source Video URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("🚀 Run Pipeline", type="primary"):
    if not all([GITHUB_TOKEN, REPO_OWNER, REPO_NAME, video_url]):
        st.error("Please fill in all GitHub credentials and the video URL in the sidebar and main form.")
    else:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        dispatch_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches"
        payload = {
            "ref": "main",
            "inputs": {"video_url": video_url}
        }
        
        with st.spinner("Dispatching pipeline job to GitHub Actions..."):
            response = requests.post(dispatch_url, headers=headers, json=payload)
            
        if response.status_code == 204:
            st.success("Pipeline triggered successfully! Waiting for runner to pick up task...")
            
            # Poll GitHub Actions for latest run ID
            runs_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1"
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
                log_placeholder = st.empty()
                status_placeholder = st.empty()
                
                # Polling loop for status and logs
                while True:
                    time.sleep(5)
                    run_status_res = requests.get(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}", headers=headers).json()
                    status = run_status_res.get("status")
                    conclusion = run_status_res.get("conclusion")
                    
                    status_placeholder.markdown(f"**Current Status:** `{status}` | **Conclusion:** `{conclusion}`")
                    
                    if status == "completed":
                        if conclusion == "success":
                            st.success("🎉 Pipeline completed successfully!")
                            
                            # Fetch and display output artifact
                            artifacts_res = requests.get(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/artifacts", headers=headers).json()
                            artifacts = artifacts_res.get("artifacts", [])
                            if artifacts:
                                download_url = artifacts[0]["archive_download_url"]
                                st.markdown(f"📥 [Download Generated Short Artifact Archive]({download_url}) *(Requires GitHub login)*")
                        else:
                            st.error(f"Pipeline failed with conclusion: {conclusion}")
                        break
            else:
                st.warning("Could not automatically retrieve run ID, but workflow was dispatched. Check your GitHub Actions tab.")
        else:
            st.error(f"Failed to trigger workflow: {response.status_code} - {response.text}")
