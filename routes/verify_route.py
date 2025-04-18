from flask import Flask, Response, jsonify, Blueprint, request
from PIL import Image
import pytesseract
import re
import io
import requests
from fuzzywuzzy import fuzz
import json
import google.generativeai as genai

verify_bp = Blueprint('verify_bp', __name__)

with open('sample_db.json', 'r') as f:
    sample_db = json.load(f)


PINATA_API_KEY = '04b26ee360171f03ae2b'
PINATA_SECRET_API_KEY = '250fe3ce90862d18f94ced6c065a6bec5a956d528aef8ab9d737a9b3f0ca8065'

genai.configure(api_key='AIzaSyBT5ntUfk9RBtMZi34cnXqFELRpoh3_QGA')

def getGeminiResponse(ocr_data):
    inputPrompt = f"This is my OCR data of a document: {ocr_data}. Generate the key-value pairs in JSON format for: Name, Roll Number, Result, CPI."
    model = genai.GenerativeModel('gemini-1.5-flash')
    rawResponse = model.generate_content(inputPrompt)
    response = rawResponse.text.replace('\n', '').replace('*', '')
    return response

def download_image_from_ipfs(ipfs_link):
    ipfs_gateway = "https://ipfs.io/ipfs/"
    ipfs_hash = ipfs_link.split("ipfs://")[-1]
    download_url = ipfs_gateway + ipfs_hash
    response = requests.get(download_url)
    if response.status_code == 200:
        return Image.open(io.BytesIO(response.content))
    else:
        raise Exception("Failed to download image from IPFS")

def upload_to_ipfs(image_data):
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_API_KEY
    }
    files = {
        'file': ('image.jpg', io.BytesIO(image_data), 'image/jpeg')
    }
    response = requests.post(url, files=files, headers=headers)
    if response.status_code == 200:
        ipfs_hash = response.json()["IpfsHash"]
        return ipfs_hash
    else:
        raise Exception("Failed to upload to IPFS: " + response.text)

def process_image(image):
    extracted_text = pytesseract.image_to_string(image).lower()

    refined_text = getGeminiResponse(extracted_text)

    if refined_text.startswith("```"):
        refined_text = re.sub(r"```(?:json)?", "", refined_text).strip()
        refined_text = refined_text.replace("```", "").strip()

    try:
        refined_json = json.loads(refined_text)
    except json.JSONDecodeError:
        return jsonify({
            "error": "Failed to parse Gemini output as JSON",
            "raw_response": refined_text
        }), 500

    name = refined_json.get("Name", "not found").strip()
    roll_number = refined_json.get("Roll Number", "not found").strip()
    result = refined_json.get("Result", "not found").strip()
    cpi = refined_json.get("CPI", "not found").strip()

    extracted_data = {
        "Name": name,
        "Roll Number": roll_number,
        "Result": result,
        "CPI": cpi
    }

    print("Extracted Data:", extracted_data)

    db_entry = next((entry for entry in sample_db if entry["Roll Number"] == roll_number), None)

    if db_entry:
        name_match_score = fuzz.partial_ratio(name.lower(), db_entry["Name"].lower())
        result_match_score = fuzz.partial_ratio(result.lower(), db_entry["Result"].lower())
        cpi_match_score = fuzz.partial_ratio(cpi, db_entry["CPI"])

        fuzzy_results = {
            "Name Match Score": name_match_score,
            "Result Match Score": result_match_score,
            "CPI Match Score": cpi_match_score
        }

        print("Fuzzy Match Results:", fuzzy_results)

        match_result = all(score >= 90 for score in fuzzy_results.values())

        return jsonify({
            "Match Result": int(match_result),
            "Extracted Data": extracted_data,
            "Fuzzy Scores": fuzzy_results
        }), 200

    return jsonify({
        "error": "Roll Number not found in database",
        "Extracted Data": extracted_data
    }), 404

@verify_bp.route('/p', methods=['POST'])
def process_image_ipfs():
    print("Route /p was hit")
    data = request.get_json()

    if not data or 'ipfs_link' not in data:
        return jsonify({"error": "No IPFS link provided"}), 400

    ipfs_link = data['ipfs_link']

    try:
        image = download_image_from_ipfs(ipfs_link)
        return process_image(image)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
