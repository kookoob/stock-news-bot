import feedparser
import tweepy
import requests
import os
import sys
import time
import re

# ==========================================
# 1. 환경 변수 로드 (공백 제거)
# ==========================================
def get_clean_env(name):
    val = os.environ.get(name)
    if val is None: return None
    return val.strip().replace('\n', '').replace('\r', '').replace(' ', '')

GEMINI_API_KEY = get_clean_env("GEMINI_API_KEY")
CONSUMER_KEY = get_clean_env("CONSUMER_KEY")
CONSUMER_SECRET = get_clean_env("CONSUMER_SECRET")
ACCESS_TOKEN = get_clean_env("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = get_clean_env("ACCESS_TOKEN_SECRET")

# ==========================================
# 2. 트위터 클라이언트
# ==========================================
client = None
try:
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
except:
    print("⚠️ 트위터 클라이언트 생성 오류 (키 확인 필요)")

# ==========================================
# 3. AI 함수 (모델 자동 탐색 기능 탑재)
# ==========================================
def summarize_news(category, title, link):
    # 1. 사용 가능한 모델 목록 조회
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    target_model = "gemini-1.5-flash" # 기본값

    try:
        # 모델 리스트를 받아봅니다.
        list_res = requests.get(list_url)
        if list_res.status_code == 200:
            models = list_res.json().get('models', [])
            # 'generateContent' 기능을 지원하는 모델 찾기
            for m in models:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    # 모델 이름에서 'models/' 제거
                    target_model = m['name'].replace('models/', '')
                    print(f"🤖 발견된 사용 가능 모델: {target_model}")
                    break # 하나 찾으면 그걸로 결정
    except Exception as e:
        print(f"⚠️ 모델 목록 조회 실패: {e}, 기본값({target_model}) 사용")

    # 2. 찾은 모델로 요약 요청
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"뉴스 제목: {title}\n뉴스 링크: {link}\n주식 뉴스 3줄 요약 (해요체)."
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"⚠️ AI 요청 실패 (코드 {response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"⚠️ AI 연결 에러: {e}")
        return None

# ==========================================
# 4. 뉴스 처리 로직
# ==========================================
RSS_SOURCES = [
    ("미국주식(투자)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069", "last_link_us_investing.txt"),
    ("미국주식(금융)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "last_link_us_finance.txt"),
    ("미국주식(기술)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "last_link_us_tech.txt"),
    ("한국주식(한경)", "https://www.hankyung.com/feed/finance", "last_link_kr.txt")
]

def get_latest_news(rss_url):
    try:
        feed = feedparser.parse(rss_url)
        return feed.entries[0] if feed.entries else None
    except: return None

def check_if_new(last_link_file, current_link):
    if not os.path.exists(last_link_file): return True
    with open(last_link_file, 'r', encoding='utf-8') as f:
        return f.read().strip() != current_link

def save_current_link(last_link_file, current_link):
    with open(last_link_file, 'w', encoding='utf-8') as f:
        f.write(current_link)

if __name__ == "__main__":
    for category, rss_url, filename in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        news = get_latest_news(rss_url)
        
        if news and check_if_new(filename, news.link):
            print(f"✨ 뉴스 발견: {news.title}")
            
            summary = summarize_news(category, news.title, news.link)
            if not summary:
                print("🚨 AI 실패. 제목만 사용합니다.")
                summary = f"{news.title}\n(AI 응답 없음)"

            tweet_text = f"[{category}] 🚨\n\n{summary}\n\n🔗 {news.link}"
            
            try:
                client.create_tweet(text=tweet_text)
                print("✅ 트윗 업로드 성공!")
                save_current_link(filename, news.link)
            except Exception as e:
                print(f"❌ 트윗 실패: {e}")
                print("👉 402 에러라면: 트위터 프로젝트를 삭제하고 'Free'로 다시 만드세요.")
        else:
            print("새 뉴스 없음.")
        time.sleep(1)
