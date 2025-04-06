from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import fitz  
import re
import spacy
from bs4 import BeautifulSoup
import requests
from PIL import Image
from google.generativeai import configure, GenerativeModel
import json

resume_route = Blueprint("resume_route", __name__)
nlp = spacy.load("en_core_web_sm")

GEMINI_API_KEY = "AIzaSyCkKmc-XjGqBB5GBlc"
configure(api_key=GEMINI_API_KEY)
model = GenerativeModel('gemini-1.5-pro-latest')

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    return "\n".join([page.get_text() for page in doc])

def extract_links_from_pdf(file_path):
    links = []
    doc = fitz.open(file_path)
    for page_num in range(len(doc)):
        page = doc[page_num]
        annotations = page.get_links()
        for annotation in annotations:
            if annotation.get("uri"):
                links.append(annotation["uri"])
    return links

def extract_platform_and_username(url):
    if "leetcode.com/u/" in url:
        platform = "leetcode"
        username = re.search(r"/u/([^/]+)/?", url)
    elif "codeforces.com/profile/" in url:
        platform = "codeforces"
        username = re.search(r"/profile/([^/]+)/?", url)
    elif "codechef.com/users/" in url:
        platform = "codechef"
        username = re.search(r"/users/([^/]+)/?", url)
    else:
        return None, None
    return platform, username.group(1) if username else None

def get_leetcode_profile(username):
    url = "https://leetcode.com/graphql"

    query = """
    query userProfile($username: String!) {
      userContestRanking(username: $username) {
        rating
        globalRanking
        attendedContestsCount
        topPercentage
      }
      matchedUser(username: $username) {
        profile {
          reputation
          ranking
          userAvatar
          realName
          aboutMe
          school
          countryName
        }
        submitStats: submitStatsGlobal {
          acSubmissionNum {
            difficulty
            count
          }
        }
      }
    }
    """

    variables = {"username": username}
    response = requests.post(url, json={"query": query, "variables": variables})

    if response.status_code != 200:
        return {"error": "Failed to fetch data"}

    data = response.json()

    contest_data = data.get("data", {}).get("userContestRanking", {})
    profile_data = data.get("data", {}).get("matchedUser", {}).get("profile", {})
    submission_stats = data.get("data", {}).get("matchedUser", {}).get("submitStats", {}).get("acSubmissionNum", [])

    solved_questions = {}
    for item in submission_stats:
        difficulty = item.get("difficulty")
        count = item.get("count", 0)
        solved_questions[difficulty] = count

    return {
        "platform": "leetcode",
        "username": username,
        "rating": contest_data.get("rating"),
        "globalRanking": contest_data.get("globalRanking"),
        "topPercentage": contest_data.get("topPercentage"),
        "attendedContests": contest_data.get("attendedContestsCount"),
        "solvedQuestions": solved_questions,
        "reputation": profile_data.get("reputation"),
        "school": profile_data.get("school"),
        "country": profile_data.get("countryName")
    }

def get_codeforces_profile(username):
    try:
        url = f"https://codeforces.com/api/user.info?handles={username}"
        res = requests.get(url).json()
        user = res["result"][0]
        return {
            "platform": "codeforces",
            "username": user["handle"],
            "rating": user.get("rating", "N/A"),
            "maxRating": user.get("maxRating", "N/A"),
            "rank": user.get("rank", "N/A"),
            "contribution": user.get("contribution", "N/A"),
            "friendOfCount": user.get("friendOfCount", "N/A")
        }
    except:
        return None

def get_codechef_profile(username):
    try:
        url = f"https://www.codechef.com/users/{username}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        rating = soup.find("div", class_="rating-number")
        stars = soup.find("span", class_="rating-star")
        return {
            "platform": "codechef",
            "username": username,
            "rating": int(rating.text.strip()) if rating else "N/A",
            "stars": stars.text.strip() if stars else "N/A"
        }
    except:
        return None

def verify_coding_profiles(resume_text, link_array):
    results = []

    ratings_claimed = {
        "leetcode": re.search(r"Leetcode Max-Rating: (\d+)", resume_text),
        "codeforces": re.search(r"Codeforces Max-Rating: (\d+)", resume_text),
        "codechef": re.search(r"Codechef Max-Rating: (\d+)", resume_text),
    }
    ratings_claimed = {k: int(v.group(1)) if v else None for k, v in ratings_claimed.items()}

    for link in link_array:
        platform, username = extract_platform_and_username(link)
        if not platform:
            continue

        if platform == "leetcode":
            profile = get_leetcode_profile(username)
        elif platform == "codeforces":
            profile = get_codeforces_profile(username)
        elif platform == "codechef":
            profile = get_codechef_profile(username)
        else:
            continue

        if profile:
            claimed = ratings_claimed.get(platform)
            actual = profile.get("rating")
            verified = abs(claimed - actual) <= 20 if claimed and actual != "N/A" else False

            profile["claimed_rating"] = claimed
            profile["verified"] = verified

            results.append(profile)

    return results

def extract_github_links(links_array):
    return [link for link in links_array if "github.com" in link]

def extract_resume_projects(resume_text):
    doc = nlp(resume_text)
    return [sent.text.strip() for sent in doc.sents if "project" in sent.text.lower()]

def scrape_github_repo(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    repo_name = soup.find('strong', {'itemprop': 'name'})
    repo_name = repo_name.text.strip() if repo_name else "Unknown"

    description = soup.find('p', {'class': 'f4 my-3'})
    description = description.text.strip() if description else ""

    readme_section = soup.find('article', {'class': 'markdown-body entry-content container-lg'})
    readme_text = readme_section.text.strip() if readme_section else ""

    return {
        "repo_name": repo_name,
        "description": description,
        "readme": readme_text
    }

def get_github_repo_insights(github_url):
    pattern = r"github\.com/([^/]+)/([^/]+)"
    match = re.search(pattern, github_url)
    if not match:
        return {}

    user, repo = match.groups()

    headers = {
        "Accept": "application/vnd.github.v3+json"
    }

    repo_api = f"https://api.github.com/repos/{user}/{repo}"
    commits_api = f"https://api.github.com/repos/{user}/{repo}/commits"
    languages_api = f"https://api.github.com/repos/{user}/{repo}/languages"
    stats_api = f"https://api.github.com/repos/{user}/{repo}/stats/contributors"

    try:
        repo_data = requests.get(repo_api, headers=headers).json()
        commits_data = requests.get(commits_api, headers=headers).json()
        langs_data = requests.get(languages_api, headers=headers).json()
        stats_data = requests.get(stats_api, headers=headers).json()

        total_commits = len(commits_data) if isinstance(commits_data, list) else "N/A"
        additions = 0
        deletions = 0
        if isinstance(stats_data, list):
            for contributor in stats_data:
                additions += contributor['weeks'][0]['a']
                deletions += contributor['weeks'][0]['d']

        return {
            "full_name": repo_data.get("full_name"),
            "stars": repo_data.get("stargazers_count"),
            "forks": repo_data.get("forks_count"),
            "watchers": repo_data.get("watchers_count"),
            "open_issues": repo_data.get("open_issues_count"),
            "total_commits": total_commits,
            "languages_used": list(langs_data.keys()),
            "additions_first_week": additions,
            "deletions_first_week": deletions
        }

    except:
        return {}

def semantic_similarity(text1, text2):
    doc1 = nlp(text1)
    doc2 = nlp(text2)
    return doc1.similarity(doc2)

def match_resume_projects_to_github(resume_text, links_array):
    resume_projects = extract_resume_projects(resume_text)
    github_links = extract_github_links(links_array)

    matched_projects = []

    for git_link in github_links:
        repo_data = scrape_github_repo(git_link)
        if not repo_data:
            continue

        combined_text = f"{repo_data['repo_name']} {repo_data['description']} {repo_data['readme']}"

        best_match = {"score": 0, "resume_project": ""}
        for rp in resume_projects:
            rp = rp.lower()
            combined_text = combined_text.lower()
            sim_score = semantic_similarity(rp, combined_text)
            if sim_score > best_match["score"]:
                best_match["score"] = sim_score
                best_match["resume_project"] = rp

        repo_insights = get_github_repo_insights(git_link)

        matched_projects.append({
            "resume_project": best_match["resume_project"],
            "github_repo_url": git_link,
            "similarity_score": round(best_match["score"], 3),
            "verified": best_match["score"] > 0.75,
            "repo_data": repo_data,
            "repo_insights": repo_insights
        })

    return matched_projects

def get_direct_download_link(drive_url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
    if not match:
        match = re.search(r'id=([a-zA-Z0-9_-]+)', drive_url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return None

def download_file_from_drive(drive_url, filename="temp.pdf"):
    download_url = get_direct_download_link(drive_url)
    if not download_url:
        return None
    response = requests.get(download_url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        return filename
    return None

def analyze_with_gemini(text):
    prompt = f"""
You are an expert document analyzer. Given a scanned document text, do the following:
1. Identify if it's a **Letter of Recommendation (LOR)** or a **Certificate**.
2. Extract structured data accordingly.

If LOR:
- Candidate Name
- Recommender Email
- Reference Number
- Institution Name
- Purpose of recommendation
- Sentiment of the letter (positive/neutral/negative)

If Certificate:
- Issuing Company
- Topic/Skill
- Duration
- Level (basic/intermediate/advanced)
- Reference Number
- Date of Issue

TEXT:
---
{text}
---

Respond in JSON format only.
"""
    response = model.generate_content(prompt)
    try:
        return eval(response.text.strip())
    except:
        return {"error": "Could not parse Gemini output", "raw": response.text}

def process_certificate_or_lor(drive_link):
    pdf_file = download_file_from_drive(drive_link)
    if not pdf_file:
        return {"error": "File download failed"}

    text = extract_text_from_pdf(pdf_file)
    os.remove(pdf_file)

    insights = analyze_with_gemini(text)
    return insights

def verify_lor_certificates(links_array):
    results = []
    for link in links_array:
        if "drive.google.com" in link:
            result = process_certificate_or_lor(link)
            results.append(result)
    return results

@resume_route.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"})
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        resume_text = extract_text_from_pdf(file_path)
        links_array = extract_links_from_pdf(file_path)

        verified_profiles = verify_coding_profiles(resume_text, links_array)

        matched_projects = match_resume_projects_to_github(resume_text, links_array)

        lor_certificates = verify_lor_certificates(links_array)

        results = {
            "verified_profiles": verified_profiles,
            "matched_projects": matched_projects,
            "lor_certificates": lor_certificates
        }

        return jsonify(results)

    return jsonify({"error": "Invalid file format"})