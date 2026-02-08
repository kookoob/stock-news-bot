#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
테스트용 트윗 데이터 생성
"""

import json
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# 출력 디렉토리
OUTPUT_DIR = "twitter_queue"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_test_image():
    """간단한 테스트 이미지 생성"""
    width, height = 1200, 675
    
    # 배경 그라데이션
    image = Image.new('RGB', (width, height), (15, 30, 45))
    draw = ImageDraw.Draw(image, 'RGBA')
    
    # 폰트 로드 (없으면 기본 폰트)
    try:
        font_title = ImageFont.truetype("font_bold.ttf", 80)
        font_body = ImageFont.truetype("font_reg.ttf", 40)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
    
    # 제목
    title = "🧪 OpenClaw 테스트"
    draw.text((60, 200), title, font=font_title, fill=(0, 220, 255))
    
    # 본문
    body_lines = [
        "✅ 브라우저 자동화 테스트",
        "✅ Twitter API 대신 사람처럼 포스팅",
        "✅ 알고리즘 패널티 없음"
    ]
    
    y_pos = 320
    for line in body_lines:
        draw.text((60, y_pos), line, font=font_body, fill=(245, 245, 250))
        y_pos += 70
    
    # 하단 정보
    timestamp = datetime.now().strftime("%Y.%m.%d %H:%M")
    draw.text((60, 580), f"📅 {timestamp} | Powered by OpenClaw", 
              font=font_body, fill=(200, 200, 210))
    
    # 저장
    img_path = os.path.join(OUTPUT_DIR, "test_image.png")
    image.save(img_path)
    print(f"✅ 이미지 생성: {img_path}")
    return img_path

def create_test_tweet():
    """테스트용 트윗 JSON 생성"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 이미지 생성
    img_path = create_test_image()
    
    # 트윗 텍스트
    tweet_text = """🧪 OpenClaw 브라우저 자동화 테스트

📋 이 트윗은 OpenClaw가 브라우저를 통해 자동으로 작성했습니다.

✅ Twitter API 대신 사람처럼 포스팅
✅ 알고리즘 패널티 회피
✅ 랜덤 딜레이로 자연스럽게

#OpenClaw #테스트 #자동화"""
    
    # JSON 데이터
    queue_data = {
        "text": tweet_text,
        "images": [img_path],
        "created_at": timestamp,
        "is_test": True
    }
    
    # JSON 파일 저장
    json_path = os.path.join(OUTPUT_DIR, f"tweet_{timestamp}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(queue_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 트윗 데이터 생성: {json_path}")
    print(f"📝 텍스트 길이: {len(tweet_text)} 자")
    print(f"🖼️ 이미지: 1개")
    
    return json_path

if __name__ == "__main__":
    print("🧪 테스트용 트윗 데이터 생성 중...")
    json_path = create_test_tweet()
    print(f"\n🚀 준비 완료! OpenClaw가 이제 포스팅할 수 있습니다.")
    print(f"   파일: {json_path}")
