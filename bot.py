import feedparser
import tweepy
import requests
import os
import sys
import time
import textwrap
from PIL import Image, ImageDraw, ImageFont # 이미지 처리를 위한 라이브러리

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
# 2. 트위터 클라이언트 (v2 + v1.1 미디어용)
# ==========================================
client = None
api = None # 이미지 업로드를 위한 v1.1 API 객체

try:
    # V2 Client (글쓰기용)
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
    # V1.1 API (이미지 업로드용 - 필수)
    auth = tweepy.OAuth1UserHandler(
        CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET
    )
    api = tweepy.API(auth)
except:
    print("⚠️ 트위터 클라이언트 생성 오류")

# ==========================================
# 3. 뉴스 소스 설정
# ==========================================
RSS_SOURCES = [
    ("미국주식(투자)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069", "last_link_us_investing.txt", "CNBC"),
    ("미국주식(금융)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "last_link_us_finance.txt", "CNBC"),
    ("미국주식(기술)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "last_link_us_tech.txt", "CNBC"),
    ("한국주식(한경)", "https://www.hankyung.com/feed/finance", "last_link_kr.txt", "한국경제"),
    ("미국주식(Yahoo)", "https://finance.yahoo.com/news/rssindex", "last_link_yahoo.txt", "Yahoo Finance"),
    ("미국주식(Tech)", "https://techcrunch.com/feed/", "last_link_techcrunch.txt", "TechCrunch"),
    ("한국주식(매경)", "https://www.mk.co.kr/rss/50200011/", "last_link_mk.txt", "매일경제"),
    ("미국주식(WSJ_Opinion)", "https://feeds.content.dowjones.io/public/rss/RSSOpinion", "last_link_wsj_op.txt", "WSJ"),
    ("미국주식(WSJ_Market)", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "last_link_wsj_mkt.txt", "WSJ"),
    ("미국주식(WSJ_Economy)", "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed", "last_link_wsj_eco.txt", "WSJ")
]

# ==========================================
# 4. 카드뉴스(인포그래픽) 생성 함수
# ==========================================
def create_info_image(text, source_name):
    try:
        # 1. 이미지 캔버스 생성 (검은 배경)
        width, height = 1080, 1080 # 인스타그램/트위터 최적 사이즈
        background_color = (20, 20, 20) # 짙은 회색/검정
        text_color = (255, 255, 255) # 흰색
        accent_color = (0, 180, 255) # 포인트 컬러 (하늘색)
        
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        
        # 2. 폰트 로드 (★중요: font.ttf 파일이 같은 폴더에 있어야 함)
        # 폰트 파일이 없으면 에러가 나므로, 없으면 기본 폰트 시도 (하지만 한글 깨질 수 있음)
        font_path = "font.ttf" 
        try:
            title_font = ImageFont.truetype(font_path, 60)
            body_font = ImageFont.truetype(font_path, 40)
            source_font = ImageFont.truetype(font_path, 30)
        except:
            print("⚠️ 폰트 파일을 찾을 수 없습니다. 기본 폰트를 사용합니다.")
            return None # 폰트 없으면 이미지 생성 포기

        # 3. 텍스트 배치
        margin = 80
        current_h = 100
        
        # 상단 출처 표시
        draw.text((margin, 50), f"Market Radar | {source_name}", font=source_font, fill=accent_color)

        # 본문 줄바꿈 처리 및 그리기
        lines = text.split('\n')
        for line in lines:
            # 제목인 경우 (첫줄)
            if lines.index(line) == 0:
                wrapped_lines = textwrap.wrap(line, width=28) # 제목은 짧게 줄바꿈
                for wl in wrapped_lines:
                    draw.text((margin, current_h), wl, font=title_font, fill=accent_color)
                    current_h += 80
                current_h += 40 # 제목과 본문 사이 간격
                
                # 구분선 긋기
                draw.line([(margin, current_h), (width-margin, current_h)], fill=(100,100,100), width=2)
                current_h += 60
            else:
                # 본문 내용
                wrapped_lines = textwrap.wrap(line, width=40) # 본문 줄바꿈
                for wl in wrapped_lines:
                    draw.text((margin, current_h), wl, font=body_font, fill=text_color)
                    current_h += 55
            
            # 이미지가 너무 길어지면 멈춤
            if current_h > height - 100:
                break
                
        # 4. 이미지 저장
        temp_filename = "temp_news_card.png"
        image.save(temp_filename)
        return temp_filename
        
    except Exception as e:
        print(f"❌ 이미지 생성 실패: {e}")
        return None

# ==========================================
# 5. AI 요약 함수
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

    # 카드뉴스용 텍스트 작성을 위한 프롬프트 (조금 더 간결하게 수정)
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}

    이 뉴스를 '카드뉴스 이미지'에 넣을 수 있도록 텍스트를 정리해줘.
    
    [작성 규칙]
    1. 첫째 줄: 핵심 제목 (이모지 없이 한글로만, 임팩트 있게)
    2. 본문:
       - 4~5개의 핵심 문장으로 요약 (개조식)
       - 구체적 수치($) 포함 필수
       - '✅' 같은 불렛포인트 사용
       - 문장은 너무 길지 않게 (이미지에 들어가야 함)
    3. 맨 아래줄: 관련 티커 ($TSLA 등) 및 해시태그 2개
    4. 링크 절대 포함 금지
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
# 6. 메인 실행
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
            
            # 1. 텍스트 요약 생성
            summary = summarize_news(category, news.title, news.link)
            
            if summary:
                # 2. 이미지(카드뉴스) 생성
                image_file = create_info_image(summary, source_name)
                
                try:
                    media_id = None
                    # 이미지가 성공적으로 만들어졌으면 업로드
                    if image_file:
                        print("🖼️ 카드뉴스 이미지 생성 완료, 업로드 중...")
                        media = api.media_upload(image_file) # v1.1 API로 이미지 업로드
                        media_id = media.media_id
                    
                    # 3. 트윗 작성 (텍스트 + 이미지)
                    # 이미지가 있으면 media_ids에 추가, 없으면 텍스트만
                    tweet_text = f"[{category}]\n\n{summary}\n\n출처: {source_name}"
                    
                    # 12,000자 제한 컷 (텍스트용)
                    if len(tweet_text) > 12000:
                        tweet_text = tweet_text[:11995] + "..."

                    if media_id:
                        response = client.create_tweet(text=tweet_text, media_ids=[media_id])
                    else:
                        response = client.create_tweet(text=tweet_text)
                        
                    tweet_id = response.data['id']
                    print("✅ 메인 트윗(이미지 포함) 업로드 성공!")
                    
                    # 4. 링크 댓글
                    reply_text = f"🔗 원문 기사 보러가기:\n{news.link}"
                    client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                    print("✅ 링크 댓글 달기 성공!")

                    save_current_link(filename, news.link)
                    
                    # 임시 이미지 파일 삭제
                    if image_file and os.path.exists(image_file):
                        os.remove(image_file)
                    
                except Exception as e:
                    print(f"❌ 트윗 실패: {e}")
            else:
                print("🚨 AI 요약 실패로 건너뜀")
        else:
            print("새 뉴스 없음.")
        time.sleep(2)
