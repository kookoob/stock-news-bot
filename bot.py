import feedparser
import tweepy
import requests
import os
import sys
import time
import re # 태그 제거용

# ==========================================
# 1. 환경 변수 설정
# ==========================================
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"].strip()
    CONSUMER_KEY = os.environ["CONSUMER_KEY"].strip()
    CONSUMER_SECRET = os.environ["CONSUMER_SECRET"].strip()
    ACCESS_TOKEN = os.environ["ACCESS_TOKEN"].strip()
    ACCESS_TOKEN_SECRET = os.environ["ACCESS_TOKEN_SECRET"].strip()
except KeyError:
    print("⚠️ 환경 변수를 찾지 못해 종료합니다.")
    sys.exit(1)

# ==========================================
# 2. 뉴스 소스 설정
# ==========================================
RSS_US_INVESTING = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"
RSS_US_FINANCE   = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
RSS_US_TECH      = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"
RSS_KR = "https://www.hankyung.com/feed/finance"

# ==========================================
# 3. 트위터 인증
# ==========================================
try:
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
except Exception as e:
    print(f"❌ 트위터 로그인 실패: {e}")
    sys.exit(1)

# ==========================================
# 4. 기능 함수들
# ==========================================
def clean_html(raw_html):
    """RSS 설명글에 있는 지저분한 태그 제거"""
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

def get_latest_news(rss_url):
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return None
        return feed.entries[0]
    except Exception as e:
        print(f"⚠️ RSS 로딩 에러: {e}")
        return None

def check_if_new(last_link_file, current_link):
    if not os.path.exists(last_link_file):
        return True
    with open(last_link_file, 'r', encoding='utf-8') as f:
        last_link = f.read().strip()
    return last_link != current_link

def save_current_link(last_link_file, current_link):
    with open(last_link_file, 'w', encoding='utf-8') as f:
        f.write(current_link)

def summarize_news(category, title, link):
    # [1차 시도] AI에게 요약 요청
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"뉴스 제목: {title}\n뉴스 링크: {link}\n이 주식 뉴스를 한국어로 3줄 요약해줘. 해요체로 친절하게."
    
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"⚠️ AI 연결 실패 (코드 {response.status_code}), 비상 모드 전환...")
            return None # 실패하면 None 리턴 -> 비상 모드 발동
    except Exception:
        return None

# ==========================================
# 5. 메인 실행
# ==========================================
def process_news(category_name, rss_url, last_link_file):
    print(f"\n--- [{category_name}] 확인 중 ---")
    
    news = get_latest_news(rss_url)
    if not news:
        print("뉴스를 불러오지 못했습니다.")
        return

    if check_if_new(last_link_file, news.link):
        print(f"✨ 새 뉴스 발견: {news.title}")
        
        # 1. AI 요약 시도
        summary = summarize_news(category_name, news.title, news.link)
        
        # 2. AI 실패 시 비상 모드 (RSS 설명글 사용)
        if not summary:
            print("🚨 비상 모드: AI 대신 원문 설명글을 가져옵니다.")
            raw_desc = news.get("summary", news.get("description", "내용 없음"))
            summary = clean_html(raw_desc)[:120] + "..." # 120자로 자르기
            summary = f"{summary}\n(AI 서버 오류로 원문 요약을 전송합니다 🤖)"

        tweet_text = f"[{category_name} 속보] 🚨\n\n{summary}\n\n🔗 원문: {news.link}"
        
        try:
            client.create_tweet(text=tweet_text)
            print("✅ 트윗 업로드 성공!")
            save_current_link(last_link_file, news.link)
        except Exception as e:
            print(f"❌ 트윗 업로드 실패: {e}")
    else:
        print("새로운 뉴스가 없습니다.")

if __name__ == "__main__":
    process_news("미국주식(투자)", RSS_US_INVESTING, "last_link_us_investing.txt")
    time.sleep(2)
    process_news("미국주식(금융)", RSS_US_FINANCE, "last_link_us_finance.txt")
    time.sleep(2)
    process_news("미국주식(기술)", RSS_US_TECH, "last_link_us_tech.txt")
    time.sleep(2)
    process_news("한국주식(한경)", RSS_KR, "last_link_kr.txt")
