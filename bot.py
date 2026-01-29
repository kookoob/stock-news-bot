import feedparser
import tweepy
import requests
import os
import sys
import time
import re

# ==========================================
# 1. 환경 변수 설정 및 '공백 강제 제거'
# ==========================================
def get_clean_env(name):
    """비밀키에 붙은 숨겨진 공백, 엔터키를 강제로 삭제함"""
    val = os.environ.get(name)
    if val is None:
        print(f"❌ 치명적 오류: GitHub Secrets에 '{name}' 이름이 없습니다!")
        return None
    # 공백, 탭, 줄바꿈 모두 제거
    clean_val = val.strip().replace('\n', '').replace('\r', '').replace(' ', '')
    
    # 보안을 위해 앞 2글자만 보여주고 나머지는 가림
    masked = clean_val[:2] + "****" + clean_val[-2:] if len(clean_val) > 4 else "****"
    print(f"🔑 {name} 로드 완료: {masked} (길이: {len(clean_val)})")
    return clean_val

print("--- 🔐 비밀키 진단 시작 ---")
GEMINI_API_KEY = get_clean_env("GEMINI_API_KEY")
CONSUMER_KEY = get_clean_env("CONSUMER_KEY")
CONSUMER_SECRET = get_clean_env("CONSUMER_SECRET")
ACCESS_TOKEN = get_clean_env("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = get_clean_env("ACCESS_TOKEN_SECRET")
print("---------------------------")

# 키가 하나라도 없으면 즉시 종료
if not all([CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    print("❌ 비밀키 로드 실패. GitHub Settings > Secrets 이름을 확인하세요.")
    sys.exit(1)

# ==========================================
# 2. 트위터 인증 (진단 모드)
# ==========================================
try:
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
    # 인증 테스트: 내 정보 가져오기 시도 (v2)
    me = client.get_me()
    print(f"✅ 트위터 로그인 성공! (봇 계정: {me.data.username})")
except Exception as e:
    print(f"❌ 트위터 인증 사망: {e}")
    print("👉 401 에러라면: App Permissions가 'Read/Write'인지, 키를 재생성 했는지 확인 필요.")
    # 인증 실패해도 일단 뉴스 수집은 시도하도록 넘어감 (로그 확인용)

# ==========================================
# 3. 뉴스 소스 설정
# ==========================================
RSS_US_INVESTING = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"
RSS_US_FINANCE   = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
RSS_US_TECH      = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"
RSS_KR = "https://www.hankyung.com/feed/finance"

# ==========================================
# 4. 기능 함수들
# ==========================================
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def get_latest_news(rss_url):
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries: return None
        return feed.entries[0]
    except: return None

def check_if_new(last_link_file, current_link):
    if not os.path.exists(last_link_file): return True
    with open(last_link_file, 'r', encoding='utf-8') as f:
        return f.read().strip() != current_link

def save_current_link(last_link_file, current_link):
    with open(last_link_file, 'w', encoding='utf-8') as f:
        f.write(current_link)

def summarize_news(category, title, link):
    # 비상용 무료 AI 모델들 순회
    models = ["gemini-1.5-flash", "gemini-pro"]
    
    prompt = f"뉴스 제목: {title}\n뉴스 링크: {link}\n주식 뉴스 3줄 요약 (해요체)."
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(url, headers=headers, json=data)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text']
        except: continue
    return None

# ==========================================
# 5. 메인 실행
# ==========================================
def process_news(category_name, rss_url, last_link_file):
    print(f"\n--- [{category_name}] ---")
    news = get_latest_news(rss_url)
    if not news: return

    if check_if_new(last_link_file, news.link):
        print(f"✨ 발견: {news.title}")
        summary = summarize_news(category_name, news.title, news.link)
        
        if not summary:
            print("🚨 AI 실패 -> 원문 제목 사용")
            summary = f"{news.title}\n(AI 오류로 제목만 전송)"

        tweet_text = f"[{category_name}] 🚨\n\n{summary}\n\n🔗 {news.link}"
        
        try:
            client.create_tweet(text=tweet_text)
            print("✅ 업로드 성공!")
            save_current_link(last_link_file, news.link)
        except Exception as e:
            print(f"❌ 업로드 실패: {e}")
    else:
        print("새 뉴스 없음.")

if __name__ == "__main__":
    process_news("미국주식(투자)", RSS_US_INVESTING, "last_link_us_investing.txt")
    time.sleep(1)
    process_news("미국주식(금융)", RSS_US_FINANCE, "last_link_us_finance.txt")
    time.sleep(1)
    process_news("미국주식(기술)", RSS_US_TECH, "last_link_us_tech.txt")
    time.sleep(1)
    process_news("한국주식(한경)", RSS_KR, "last_link_kr.txt")
