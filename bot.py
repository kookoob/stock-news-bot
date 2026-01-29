import feedparser
import tweepy
import google.generativeai as genai  # 공식 도구 사용
import os
import sys
import time
import re

# ==========================================
# 1. 환경 변수 및 공백 제거 (유지)
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
# 2. AI 설정 (여기가 핵심!)
# ==========================================
# 파이썬 3.10이라서 이제 이 공식 도구가 잘 작동합니다.
try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"❌ AI 설정 실패: {e}")

# ==========================================
# 3. 트위터 설정
# ==========================================
try:
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
except:
    pass # 트위터 에러는 일단 무시 (AI 확인이 먼저니까)

# 뉴스 소스
RSS_SOURCES = [
    ("미국주식(투자)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069", "last_link_us_investing.txt"),
    ("미국주식(금융)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "last_link_us_finance.txt"),
    ("미국주식(기술)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "last_link_us_tech.txt"),
    ("한국주식(한경)", "https://www.hankyung.com/feed/finance", "last_link_kr.txt")
]

# ==========================================
# 4. 기능 함수들
# ==========================================
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

def summarize_news(category, title, link):
    """
    공식 도구로 3가지 모델을 순서대로 다 찔러봅니다.
    """
    models_to_try = ['gemini-1.5-flash', 'gemini-pro', 'gemini-1.0-pro-latest']
    
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}
    위 주식 뉴스를 한국어로 3줄 요약해줘.
    말투는 '해요체'로 친절하게.
    """

    for model_name in models_to_try:
        try:
            print(f"🤖 AI 시도 중... (모델: {model_name})")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            
            if response.text:
                print(f"🎉 AI 요약 성공! ({model_name})")
                return response.text
        except Exception as e:
            print(f"⚠️ {model_name} 실패: {e}")
            continue # 다음 모델 시도
            
    return None

# ==========================================
# 5. 메인 실행
# ==========================================
if __name__ == "__main__":
    for category, rss_url, filename in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        news = get_latest_news(rss_url)
        
        if news and check_if_new(filename, news.link):
            print(f"✨ 뉴스 발견: {news.title}")
            
            # 1. AI 요약 시도
            summary = summarize_news(category, news.title, news.link)
            
            # 2. 실패시 비상 문구
            if not summary:
                print("🚨 모든 AI 모델 실패. 제목만 사용합니다.")
                summary = f"{news.title}\n(AI 서버 응답 없음)"

            # 3. 트윗 작성
            tweet_text = f"[{category}] 🚨\n\n{summary}\n\n🔗 {news.link}"
            
            try:
                client.create_tweet(text=tweet_text)
                print("✅ 트윗 업로드 성공!")
                save_current_link(filename, news.link)
            except Exception as e:
                # 트위터 에러 메시지를 있는 그대로 출력
                print(f"❌ 트윗 실패: {e}")
        else:
            print("새 뉴스 없음.")
        
        time.sleep(1)
