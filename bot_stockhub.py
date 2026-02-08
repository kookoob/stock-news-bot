#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StockHub RSS 기반 트위터 뉴스봇
- https://stockhub.kr/rss 사용
- 이미 번역/요약/티커 추출 완료된 데이터 활용
- 트윗 + 댓글로 출처 링크 4개 추가
"""

import feedparser
import tweepy
import requests
import os
import time
import textwrap
import re
import random
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont

# ========================================
# 1. 환경 변수
# ========================================
def get_clean_env(name):
    val = os.environ.get(name)
    if val is None:
        return None
    return val.strip().replace('\r', '').replace('\n', '')

CONSUMER_KEY = get_clean_env("CONSUMER_KEY")
CONSUMER_SECRET = get_clean_env("CONSUMER_SECRET")
ACCESS_TOKEN = get_clean_env("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = get_clean_env("ACCESS_TOKEN_SECRET")

# ========================================
# 2. 트위터 클라이언트
# ========================================
client = tweepy.Client(
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

auth = tweepy.OAuth1UserHandler(
    CONSUMER_KEY, CONSUMER_SECRET,
    ACCESS_TOKEN, ACCESS_TOKEN_SECRET
)
api = tweepy.API(auth)

# ========================================
# 3. 중복 방지
# ========================================
POSTED_LINKS_FILE = "posted_stockhub_links.txt"

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE):
        return set()
    with open(POSTED_LINKS_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f.readlines())

def save_posted_link(link):
    with open(POSTED_LINKS_FILE, 'a', encoding='utf-8') as f:
        f.write(link + '\n')

# ========================================
# 4. StockHub RSS 파싱
# ========================================
def fetch_stockhub_rss():
    """StockHub RSS에서 최신 뉴스 가져오기"""
    rss_url = "https://stockhub.kr/rss"
    
    try:
        feed = feedparser.parse(rss_url)
        news_items = []
        
        for entry in feed.entries[:20]:  # 최신 20개
            news_items.append({
                'title': entry.title,
                'link': entry.link,
                'summary': entry.get('description', entry.title),
                'source': entry.get('source', 'StockHub'),
                'tickers': entry.get('category', '').split(', ') if entry.get('category') else [],
                'pubdate': entry.get('published', '')
            })
        
        return news_items
    except Exception as e:
        print(f"❌ RSS 파싱 오류: {e}")
        return []

# ========================================
# 5. 이미지 생성
# ========================================
def create_gradient_background(width, height, start_color, end_color):
    base = Image.new('RGB', (width, height), start_color)
    top = Image.new('RGB', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        mask_data.extend([int(255 * (y / height))] * width)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def create_news_card(title, summary_lines, source, index):
    """뉴스 카드 이미지 생성"""
    try:
        width, height = 1200, 675
        
        THEMES = [
            {"start": (10, 25, 45), "end": (20, 40, 70), "accent": (0, 220, 255)},
            {"start": (20, 20, 20), "end": (50, 50, 50), "accent": (255, 215, 0)},
            {"start": (15, 30, 25), "end": (30, 60, 50), "accent": (0, 255, 150)},
            {"start": (40, 10, 15), "end": (70, 20, 30), "accent": (255, 100, 100)},
            {"start": (25, 15, 40), "end": (50, 30, 80), "accent": (200, 100, 255)}
        ]
        
        theme = random.choice(THEMES)
        image = create_gradient_background(width, height, theme["start"], theme["end"])
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # 폰트 로드
        try:
            font_title = ImageFont.truetype("font_bold.ttf", 55)
            font_body = ImageFont.truetype("font_reg.ttf", 32)
            font_header = ImageFont.truetype("font_bold.ttf", 26)
            font_date = ImageFont.truetype("font_reg.ttf", 26)
        except:
            try:
                font_title = ImageFont.truetype("font.ttf", 50)
                font_body = ImageFont.truetype("font.ttf", 30)
                font_header = ImageFont.truetype("font.ttf", 24)
                font_date = ImageFont.truetype("font.ttf", 24)
            except:
                return None
        
        margin_x = 60
        current_y = 40
        
        # 헤더
        header_text = f"Koob | News {index}"
        if source:
            header_text += f" | {source}"
        draw.ellipse([(margin_x, current_y+8), (margin_x+12, current_y+20)], fill=theme["accent"])
        draw.text((margin_x + 25, current_y), header_text, font=font_header, fill=theme["accent"])
        
        # 날짜
        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        date_str = f"{now.year}.{now.month:02d}.{now.day:02d} | @kimyg002"
        date_bbox = draw.textbbox((0, 0), date_str, font=font_date)
        date_width = date_bbox[2] - date_bbox[0]
        draw.text((width - margin_x - date_width, current_y), date_str, font=font_date, fill=(200, 200, 210))
        
        current_y += 70
        
        # 제목
        wrapped_title = textwrap.wrap(title, width=22)
        title_box_height = len(wrapped_title) * 80 + 30
        draw.rectangle([(margin_x - 20, current_y), (width - margin_x + 20, current_y + title_box_height)], 
                      fill=(0, 0, 0, 80))
        current_y += 20
        
        for line in wrapped_title:
            draw.text((margin_x, current_y), line, font=font_title, fill=(245, 245, 250))
            current_y += 80
        
        current_y += 40
        
        # 요약
        for line in summary_lines[:3]:  # 최대 3줄
            if not line.strip():
                continue
            bullet_y = current_y + 12
            draw.rectangle([margin_x, bullet_y, margin_x + 10, bullet_y + 10], fill=theme["accent"])
            
            wrapped = textwrap.wrap(line, width=42)
            for wl in wrapped:
                draw.text((margin_x + 35, current_y), wl, font=font_body, fill=(245, 245, 250))
                current_y += 45
            current_y += 15
        
        # 하단 라인
        draw.rectangle([(margin_x, height - 20), (width - margin_x, height - 18)], fill=theme["accent"])
        
        temp_filename = f"temp_stockhub_{index}.png"
        image.convert("RGB").save(temp_filename)
        return temp_filename
    
    except Exception as e:
        print(f"❌ 이미지 생성 오류: {e}")
        return None

# ========================================
# 6. 메인 실행
# ========================================
if __name__ == "__main__":
    print("🔄 StockHub RSS 수집 시작...")
    
    # RSS 파싱
    all_news = fetch_stockhub_rss()
    
    if not all_news:
        print("📭 새로운 뉴스가 없습니다.")
        exit(0)
    
    # 중복 제거
    posted_links = get_posted_links()
    new_news = [n for n in all_news if n['link'] not in posted_links]
    
    if not new_news:
        print("📭 모두 이미 게시된 뉴스입니다.")
        exit(0)
    
    # 최신 4개 선택
    selected_news = new_news[:4]
    print(f"✅ 선택된 뉴스: {len(selected_news)}개")
    
    # 트윗 작성
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    weekday_kor = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    time_str = now.strftime(f"%m월 %d일 ({weekday_kor}) %H:%M")
    
    tweet_text = f"📅 {time_str} 기준 | 주요 소식 정리\n\n"
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    media_ids = []
    news_links = []
    
    all_tickers = set()
    all_sources = set()
    
    # 각 뉴스 처리
    for i, news in enumerate(selected_news):
        print(f"처리 중 {i+1}/4: {news['title'][:30]}...")
        
        # 요약문 분리 (줄바꿈 기준)
        summary_lines = [line.strip() for line in news['summary'].split('\n') if line.strip()]
        
        # 이미지 생성
        img_path = create_news_card(news['title'], summary_lines, news['source'], i+1)
        
        if img_path:
            try:
                media = api.media_upload(img_path)
                media_ids.append(media.media_id)
                
                # 트윗 텍스트에 추가
                tweet_text += f"{emojis[i]} {news['title']}\n"
                
                # 요약 첫 2줄 추가
                for line in summary_lines[:2]:
                    tweet_text += f"  • {line}\n"
                
                tweet_text += "────────────────\n"
                
                # 링크 저장
                news_links.append(news['link'])
                
                # 티커 수집
                if news['tickers']:
                    all_tickers.update(news['tickers'])
                
                # 출처 수집
                if news['source']:
                    all_sources.add(news['source'])
                
                # 이미지 삭제
                if os.path.exists(img_path):
                    os.remove(img_path)
                
            except Exception as e:
                print(f"❌ 업로드 실패: {e}")
    
    if not media_ids:
        print("❌ 게시할 이미지가 없습니다.")
        exit(1)
    
    # 출처 및 태그
    if all_sources:
        sources_str = ", ".join(sorted(all_sources))
        tweet_text += f"\n출처: {sources_str}\n"
    
    # 해시태그
    base_tags = "#미국주식 #속보 #경제"
    ticker_tags = " ".join(list(all_tickers)[:10])  # 최대 10개
    tweet_text += f"\n{base_tags} {ticker_tags}"
    
    # 트윗 길이 제한
    if len(tweet_text) > 2800:
        tweet_text = tweet_text[:2795] + "..."
    
    # 트윗 게시
    try:
        response = client.create_tweet(text=tweet_text, media_ids=media_ids)
        tweet_id = response.data['id']
        print(f"✅ 트윗 게시 완료! ID: {tweet_id}")
        
        # 게시된 링크 저장
        for link in news_links:
            save_posted_link(link)
        
        # 댓글로 출처 링크 추가
        if news_links:
            comment_text = "📰 자세한 내용:\n\n"
            for i, link in enumerate(news_links, 1):
                comment_text += f"{i}. {link}\n"
            
            try:
                client.create_tweet(
                    text=comment_text,
                    in_reply_to_tweet_id=tweet_id
                )
                print("✅ 출처 링크 댓글 추가 완료!")
            except Exception as e:
                print(f"⚠️ 댓글 추가 실패: {e}")
        
        print("🎉 모든 작업 완료!")
        
    except Exception as e:
        print(f"❌ 트윗 게시 실패: {e}")
