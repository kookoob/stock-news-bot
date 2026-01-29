import feedparser
import tweepy
import requests
import os
import sys
import time
import re

# ==========================================
# 1. 환경 변수 로드
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
    print("⚠️ 트위터 클라이언트 생성 오류")

# ==========================================
# 3. 뉴스 소스 설정 (매일경제 링크 교체됨)
# ==========================================
RSS_SOURCES = [
    ("미국주식(투자)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069", "last_link_us_investing.txt", "CNBC"),
    ("미국주식(금융)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "last_link_us_finance.txt", "CNBC"),
    ("미국주식(기술)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "last_link_us_tech.txt", "CNBC"),
    ("한국주식(한경)", "https://www.hankyung.com/feed/finance", "last_link_kr.txt", "한국경제"),
    ("미국주식(Yahoo)", "https://finance.yahoo.com/news/rssindex", "last_link_yahoo.txt", "Yahoo Finance"),
    ("미국주식(MW)", "http://feeds.marketwatch.com/marketwatch/topstories/", "last_link_mw.txt", "MarketWatch"),
    ("미국주식(Tech)", "https://techcrunch.com/feed/", "last_link_techcrunch.txt", "TechCrunch"),
    
    # [수정됨] 매일경제 RSS 링크 교체 (30100041 -> 50200011)
    ("한국주식(매경)", "https://www.mk.co.kr/rss/50200011/", "last_link_mk.txt", "매일경제")
]

# ==========================================
# 4. AI 요약 함수 (장문 프리미엄 모드)
# ==========================================
def summarize_news(category, title, link):
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    target_model = "gemini-1.5-flash"

    try:
        list_res = requests.get(list_url)
        if list_res.status_code == 200:
            models = list_res.json().get('models', [])
            for m in models:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    target_model = m['name'].replace('models/', '')
                    break
    except: pass

    # AI 프롬프트: 상세 분석 및 장문 작성 요구
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}

    위 뉴스 내용을 바탕으로 트위터(X) 프리미엄용 장문 포스팅을 작성해줘.
    
    [작성 규칙]
    1. 첫째 줄: 기사의 원래 제목을 '한국어'로 완벽하게 번역해서 적을 것. (이모지 1개 포함)
    2. 본문:
       - 글자 수에 구애받지 말고, 기사의 내용을 **최대한 상세하게** 작성할 것.
       - 기사에 포함된 모든 **구체적인 수치, 데이터, 기업명**을 빠짐없이 포함할 것.
       - 단순 요약이 아니라, 이 뉴스가 시장에 미칠 영향이나 배경까지 깊이 있게 설명할 것.
       - 가독성을 위해 문단(엔터)을 자주 나누고, 글 머리 기호(✅, 👉 등)를 적절히 사용할 것.
       - 축약체를 사용하되(함, 음, 등), 전문적인 어조를 유지할 것.
       - 본문 하단에는 관련 주식의 티커($)를 달 것. 기사에서 직접적으로 언급된 회사의 주식은 절대 빠트리지 말 것.
       - 해시태그(#)는 기사에서 메인이 되는 회사이름, 인물이름, 기업이름 정도만 3개 이내로 달 것.
    3. 링크나 URL은 절대 포함하지 말 것 (댓글로 달 예정).
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        return None
    except: return None

# ==========================================
# 5. 메인 실행 (프리미엄 12,500자 제한)
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

if __name__ == "__main__":
    for category, rss_url, filename, source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        news = get_latest_news(rss_url)
        
        if news and check_if_new(filename, news.link):
            print(f"✨ 뉴스 발견: {news.title}")
            
            summary = summarize_news(category, news.title, news.link)
            
            if summary:
                tweet_text = f"{summary}\n\n출처: {source_name}"
                
                # 프리미엄 한도(한글 12,500자) 적용 (안전하게 12,000자 컷)
                if len(tweet_text) > 12000:
                    tweet_text = tweet_text[:11995] + "..."
                
                try:
                    # 1. 메인 트윗 업로드
                    response = client.create_tweet(text=tweet_text)
                    tweet_id = response.data['id']
                    print("✅ 메인 트윗 업로드 성공!")
                    
                    # 2. 링크 댓글 달기
                    reply_text = f"🔗 원문 기사 보러가기:\n{news.link}"
                    client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                    print("✅ 링크 댓글 달기 성공!")

                    save_current_link(filename, news.link)
                    
                except Exception as e:
                    print(f"❌ 트윗 실패: {e}")
                    if "too long" in str(e).lower():
                         print("👉 봇 계정이 '프리미엄'이 아니면 긴 글을 올릴 수 없습니다.")
            else:
                print("🚨 AI 요약 실패로 건너뜀")
        else:
            print("새 뉴스 없음.")
        time.sleep(2)

