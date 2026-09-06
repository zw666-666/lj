"""调用豆包视觉模型描述图片"""
import base64, json, sys, os

img_path = sys.argv[1]
question = sys.argv[2] if len(sys.argv) > 2 else "描述这张图片的内容"

with open(img_path, 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()

api_key = os.environ.get("VISION_API_KEY", "")
base_url = os.environ.get("VISION_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
model = os.environ.get("VISION_MODEL", "doubao-seed-2-0-pro-260215")

import urllib.request

data = json.dumps({
    'model': model,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{img_b64}'}},
            {'type': 'text', 'text': question}
        ]
    }]
}).encode()

req = urllib.request.Request(f'{base_url}/chat/completions', data=data, headers={
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}'
})

with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read())
    content = result['choices'][0]['message']['content']
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(content)
