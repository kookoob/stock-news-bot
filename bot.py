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
# 3. 뉴스 소스 설정 (기존 목록에 아래 내용 추가)
# ==========================================
RSS_SOURCES = [
    # --- [기존 소스들] ---
    ("미국주식(투자)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069", "last_link_us_investing.txt", "CNBC"),
    ("미국주식(금융)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "last_link_us_finance.txt", "CNBC"),
    ("미국주식(기술)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "last_link_us_tech.txt", "CNBC"),
    ("한국주식(한경)", "https://www.hankyung.com/feed/finance", "last_link_kr.txt", "한국경제"),

    # --- [✨ 새로 추가할 추천 소스 ✨] ---
    # 1. 야후 파이낸스 (뉴스량 많음)
    ("미국주식(Yahoo)", "https://finance.yahoo.com/news/rssindex", "last_link_yahoo.txt", "Yahoo Finance"),
    
    # 2. 마켓워치 (핵심 이슈 위주)
    ("미국주식(MW)", "http://feeds.marketwatch.com/marketwatch/topstories/", "last_link_mw.txt", "MarketWatch"),
    
    # 3. 테크크런치 (기술/AI)
    ("미국주식(Tech)", "https://techcrunch.com/feed/", "last_link_techcrunch.txt", "TechCrunch"),

    # 4. 매일경제 (증권)
    ("한국주식(매경)", "https://www.mk.co.kr/rss/30100041/", "last_link_mk.txt", "매일경제")
]

# ==========================================
# 4. AI 요약 함수 (선생님 수정 버전 유지)
# ==========================================
def summarize_news(category, title, link):
    # 모델 자동 탐색
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    target_model = "gemini-1.5-flash" # 기본값

    try:
        list_res = requests.get(list_url)
        if list_res.status_code == 200:
            models = list_res.json().get('models', [])
            for m in models:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    target_model = m['name'].replace('models/', '')
                    break
    except: pass

    # 선생님이 작성하신 프롬프트 (그대로 유지)
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}

    위 뉴스 내용을 바탕으로 트위터에 올릴 글을 작성해줘.
    
    [작성 규칙]
    1. 첫째 줄: 기사의 원래 제목을 '한국어'로 완벽하게 번역해서 적을 것. (이모지 1개 포함)
    2. 본문: 기사의 핵심 내용을 아래의 규칙을 준수해서 요약할 것.
       - 각 포인트의 문장 앞부분에 적절한 이모지 사용.
       - 문장은 간결하고 명확하게 작성할 것.
       - 오로지 기사의 내용만 요약 및 정리
       - 축약체를 사용할 것. (증가. 감소. 발표. ~함. ~중. 이런식으로)
       - 본문 하단에는 관련 주식의 티커와 해시태그를 붙여줘 (예시 : $TSLA #TESLA #테슬라)
    3. 링크나 URL은 절대 포함하지 말 것 (내가 따로 댓글로 달 거임).
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
# 5. 메인 실행 (태그 삭제 및 답글 기능 적용)
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
                # [수정됨] 카테고리 태그 '[category]'를 제거했습니다.
                # 제목(summary 첫줄)부터 바로 시작합니다.
                tweet_text = f"{summary}\n\n출처: {source_name}"
                
                try:
                    # 1. 메인 트윗 업로드 (결과를 response 변수에 저장)
                    response = client.create_tweet(text=tweet_text)
                    
                    # 2. 방금 올린 트윗의 ID(주민번호) 추출
                    tweet_id = response.data['id']
                    print("✅ 메인 트윗 업로드 성공!")
                    
                    # 3. 그 ID 밑에 댓글(답글)로 링크 달기
                    reply_text = f"🔗 원문 기사 보러가기:\n{news.link}"
                    client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                    print("✅ 링크 댓글 달기 성공!")

                    # 4. 저장
                    save_current_link(filename, news.link)
                    
                except Exception as e:
                    print(f"❌ 트윗 실패: {e}")
            else:
                print("🚨 AI 요약 실패로 건너뜀")
        else:
            print("새 뉴스 없음.")
        time.sleep(2)

