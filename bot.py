import feedparser
import tweepy
import requests  # 구글 라이브러리 대신 직접 접속하는 도구
import os
import sys
import time
import json

# ==========================================
# 1. 환경 변수 설정
# ==========================================
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    CONSUMER_KEY = os.environ["CONSUMER_KEY"]
    CONSUMER_SECRET = os.environ["CONSUMER_SECRET"]
    ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
    ACCESS_TOKEN_SECRET = os.environ["ACCESS_TOKEN_SECRET"]
except KeyError:
    print("⚠️ 환경 변수를 찾지 못해 종료합니다.")
    sys.exit(1)

# ==========================================
# 2. 설정 값 (뉴스 소스)
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
# 4. 핵심 기능 함수들
# ==========================================
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
    """
    [핵심 변경] 죽은 라이브러리 대신 '직통 연결'로 요약 요청
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    너는 주식 시장 전문가 '마켓 레이더'야. 
    아래 뉴스 제목을 보고 한국인 투자자들이 이해하기 쉽게 3줄로 요약해줘.
    
    [규칙]
    1. 첫 줄은 내용을 한 문장으로 명확하게 설명할 것.
    2. 두 번째 줄은 이 뉴스가 시장에 미칠 영향이나 주목할 점을 언급할 것.
    3. 세 번째 줄은 재치 있는 한마디나 격언, 또는 이모지를 포함한 코멘트를 달 것.
    4. 말투는 친절하고 전문적이지만 딱딱하지 않게 해요체(~해요)를 쓸 것.
    5. 카테고리({category})에 맞는 전문성을 보여줄 것.
    6. 전체 길이는 150자를 넘지 말 것.

    뉴스 제목: {title}
    뉴스 링크: {link}
    """
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"⚠️ AI 요청 에러 (코드 {response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"⚠️ 연결 실패: {e}")
        return None

# ==========================================
# 5. 메인 실행 로직
# ==========================================
def process_news(category_name, rss_url, last_link_file):
    print(f"\n--- [{category_name}] 확인 중 ---")
    
    news = get_latest_news(rss_url)
    if not news:
        print("뉴스를 불러오지 못했습니다.")
        return

    if check_if_new(last_link_file, news.link):
        print(f"✨ 새 뉴스 발견: {news.title}")
        
        summary = summarize_news(category_name, news.title, news.link)
        if not summary:
            return

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

