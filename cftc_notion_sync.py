import os
import requests
import re
import json
from datetime import datetime
from cme_parsers.cftc_long import parse_cftc_long

# 环境变量读取
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
REPO_NAME = os.environ.get("GITHUB_REPO") 

# CFTC Metals and Other 独立直链
CFTC_URL = "https://www.cftc.gov/dea/options/other_lof.htm"

def process_file_and_notion():
    print("Downloading Metals & Other report from CFTC...")
    response = requests.get(CFTC_URL, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    text_content = response.text
    
    # 1. 精准提取文件中的客观确切时间
    match = re.search(r"Options and Futures Combined, ([A-Za-z]+ \d{1,2}, \d{4})", text_content)
    
    if not match:
        print("Error: Could not extract exact date. Data fetch delayed or format changed. Marking as N/A.")
        return
        
    raw_date = match.group(1)
    # 将 "March 10, 2026" 转换为 "2026-03-10"
    parsed_date = datetime.strptime(raw_date, "%B %d, %Y").strftime("%Y-%m-%d")
    print(f"Extracted Exact Date from file: {parsed_date}")
    
    # 2. 将内容保存为本地 txt 文件
    save_dir = "data"
    os.makedirs(save_dir, exist_ok=True)
    file_name = f"CFTC_Metals_Other_Combined_{parsed_date}.txt"
    file_path = f"{save_dir}/{file_name}"
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text_content)
        
    # 3. 构造 GitHub Raw URL
    github_raw_url = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{file_path}"
    
    # 4. 解析并提取紧凑 JSON 字段
    parse_status = "OK"
    cot_json = None
    try:
        print(f"Parsing CFTC report file: {file_path}")
        parsed_data = parse_cftc_long(file_path)
        
        # 筛选 GOLD, SILVER, PLATINUM, PALLADIUM, COPPER
        cot_dict = {}
        target_keys = ["GOLD", "SILVER", "PLATINUM", "PALLADIUM"]
        for tk in target_keys:
            if tk in parsed_data:
                cot_dict[tk] = parsed_data[tk]
                if parsed_data[tk].get("status") != "OK":
                    parse_status = f"PARSE_FAILED ({tk}): {parsed_data[tk].get('status')}"
            else:
                parse_status = f"MISSING_COMMODITY_{tk}"
        
        # 铜特殊匹配 (通常包含 COPPER - COMMODITY EXCHANGE INC. 等)
        copper_key = next((k for k in parsed_data if k.startswith("COPPER")), None)
        if copper_key:
            cot_dict["COPPER"] = parsed_data[copper_key]
            if parsed_data[copper_key].get("status") != "OK":
                parse_status = f"PARSE_FAILED (COPPER): {parsed_data[copper_key].get('status')}"
        else:
            parse_status = "MISSING_COMMODITY_COPPER"
        
        cot_json = json.dumps(cot_dict, ensure_ascii=False, separators=(',', ':'))[:1900]
    except Exception as ex:
        parse_status = f"PARSE_ERROR: {str(ex)}"
    
    # 5. 更新 Notion Database
    notion_api_url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Name": {
                "title": [{"text": {"content": "CFTC Metals & Other - Combined"}}]
            },
            "Date": {
                "date": {"start": parsed_date}
            },
            "Files & media": {
                "files": [
                    {
                        "type": "external",
                        "name": file_name,
                        "external": {"url": github_raw_url}
                    }
                ]
            },
            "Parse Status": {
                "rich_text": [{"text": {"content": parse_status[:1900]}}]
            }
        }
    }
    
    # 只有当解析成功时，才回填 COT (JSON) (失败时 omit)
    if parse_status == "OK" and cot_json is not None:
        payload["properties"]["COT (JSON)"] = {
            "rich_text": [{"text": {"content": cot_json}}]
        }
    
    res = requests.post(notion_api_url, headers=headers, json=payload)
    if res.status_code == 200:
        print(f"Successfully created Notion record for {parsed_date}! Status: {parse_status}")
    else:
        print(f"Failed to update Notion: {res.text}")

if __name__ == "__main__":
    process_file_and_notion()
