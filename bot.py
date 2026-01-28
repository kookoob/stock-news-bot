import feedparser
import tweepy
import google.generativeai as genai
import os
import sys

# ==========================================
# 1. 환경 변수 설정 (GitHub Secrets)
# ==========================================
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    CONSUMER_KEY = os.environ["CONSUMER_KEY"]
    CONSUMER_SECRET = os.environ["CONSUMER_SECRET"]
    ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
    ACCESS_TOKEN_SECRET = os.environ["ACCESS_TOKEN_SECRET"]
except KeyError:
    print("⚠️ 환경 변수를 찾지 못해 테스트 모드로 실행하거나 종료합니다.")
    # 실제 배포 시에는 아래 주석을 풀어주는 것이 안전합니다
    # sys.exit(1)

# ==========================================
# 2. 뉴스 소스 설정 (미국 + 한국)
# ==========================================
SOURCES = [
    {
        "name": "미국주식(CNBC)",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "file": "last_link_us.txt",
        "context": "미국",
        "tags": "#미국주식 #나스닥 #뉴욕증시"
    },
    {
        "name": "한국주식(한경)",
        "url": "https://rss.hankyung.com/feed/market",
        "file": "last_link_kr.txt",
        "context": "한국",
        "tags": "#국내주식 #코스피 #코스닥"
    }
]

# ==========================================
# 3. 기능 정의
# ==========================================

def get_latest_news(rss_url):
    """RSS 주소에서 최신 뉴스 1개를 가져옵니다."""
    feed = feedparser.parse(rss_url)
    if feed.entries:
        entry = feed.entries[0]
        return entry.title, entry.link
    return None, None

def is_new_link(link, filename):
    """지정된 파일(filename)을 열어 중복을 확인합니다."""
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            f.write("")
            
    with open(filename, "r") as f:
        last_link = f.read().strip()

    if link == last_link:
        return False
    return True

def summarize_news(title, context, base_tags):
    """Gemini에게 요약과 $티커 추출을 요청합니다."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    너는 주식 투자 전문가야. 아래 {context} 증시 뉴스 제목을 분석해줘.

    [뉴스 제목]: {title}

    [필수 요청 사항]
    1. 한국어로 쉽고 재치있게 100자 이내로 요약할 것 (반말 모드).
    2. 제목에 언급된 기업이 있다면 해당 기업의 '티커(Ticker)'를 반드시 찾아낼 것.
       - 미국 기업 예시: Apple -> $AAPL
       - 한국 기업 예시: 삼성전자 -> $005930 (가능하면 코드로, 모르면 $삼성전자)
    3. 언급된 기업이 없다면 티커는 생략해도 됨.
    4. 출력 형식: [요약문] \n\n [관련티커] {base_tags}
    """
    
    response = model.generate_content(prompt)
    return response.text.strip()

def post_to_twitter(text, link):
    """트위터 업로드 (AI 알림 문구 추가됨)"""
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY, consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN, access_token_secret=ACCESS_TOKEN_SECRET
    )
    
    # 요청하신 AI 알림 문구
    disclaimer = "\nℹ️ AI로 자동화된 기사 번역입니다."
    
    # 본문 합치기
    full_tweet = f"{text}\n{disclaimer}\n\n🔗 {link}"
    
    try:
        client.create_tweet(text=full_tweet)
        print("✅ 트윗 업로드 성공!")
    except Exception as e:
        print(f"❌ 트윗 업로드 실패: {e}")

def save_link(link, filename):
    """처리한 뉴스를 해당 파일에 저장"""
    with open(filename, "w") as f:
        f.write(link)

# ==========================================
# 4. 메인 실행 (순차적으로 실행)
# ==========================================
if __name__ == "__main__":
    print("🤖 봇이 주식 시장을 스캔합니다...")
    
    for source in SOURCES:
        print(f"\n--- [{source['name']}] 확인 중 ---")
        
        try:
            title, link = get_latest_news(source['url'])
            
            if title:
                # 해당 소스의 전용 파일(last_link_us.txt 등)과 비교
                if is_new_link(link, source['file']):
                    print(f"✨ 새 뉴스 발견: {title}")
                    
                    # 요약 + 태그 생성
                    summary = summarize_news(title, source['context'], source['tags'])
                    print(f"📝 생성된 트윗:\n{summary}")
                    
                    # 트윗 및 저장
                    post_to_twitter(summary, link)
                    save_link(link, source['file'])
                else:
                    print("💤 이미 올린 뉴스입니다.")
            else:
                print("뉴스를 불러오지 못했습니다.")
                
        except Exception as e:
            print(f"⚠️ 에러 발생 ({source['name']}): {e}")
            continue # 에러 나도 다음 소스로 넘어감