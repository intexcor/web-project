import asyncio
import json
import aiohttp


class Kandinsky:
    URL = "https://api-key.fusionbrain.ai/"

    def __init__(self, api_key: str, secret_key: str):
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    async def get_models(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(self.URL + 'key/api/v1/models', headers=self.AUTH_HEADERS) as response:
                data = await response.json()
                return data

    async def generate(self, prompt, model, images=1, width=1024, height=1024, negativeprompt=None, style=None):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "generateParams": {
                "query": f"{prompt}"
            }
        }
        if negativeprompt is not None:
            params['negativePromptUnclip'] = negativeprompt

        if style is not None:
            params['style'] = style

        data = aiohttp.FormData()
        data.add_field('model_id', str(model))
        data.add_field('params', json.dumps(params), content_type='application/json')

        async with aiohttp.ClientSession() as session:
            async with session.post(self.URL + 'key/api/v1/text2image/run', headers=self.AUTH_HEADERS,
                                    data=data) as response:
                data = await response.json()
                return data

    async def check_generation(self, request_id, attempts=10, delay=10):
        while attempts > 0:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.URL + 'key/api/v1/text2image/status/' + request_id,
                                       headers=self.AUTH_HEADERS) as response:
                    data = await response.json()
                    if data['status'] == 'DONE':
                        return data['images']

                    attempts -= 1
                    await asyncio.sleep(delay)

    async def generate_img(self, prompt: str, model="default", images=1, width=1024, height=1024, negativeprompt=None,
                           style=None):
        if model == "default":
            models = await self.get_models()
            model = models[0]["id"]
        data = await self.generate(prompt, model, images=images, width=width, height=height,
                                   negativeprompt=negativeprompt, style=style)
        img = await self.check_generation(data['uuid'])
        return img[0]
