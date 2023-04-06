# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import paddle

from paddlenlp.transformers import CLIPFeatureExtractor, CLIPVisionModelWithProjection
from ppdiffusers import UniDiffuserImageVariationPipeline
from ppdiffusers.models import AutoencoderKL, UViTModel
from ppdiffusers.utils import load_image

generator = paddle.Generator().manual_seed(0)

pipe = UniDiffuserImageVariationPipeline(
    image_encoder=CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-base-patch32"),
    image_feature_extractor=CLIPFeatureExtractor.from_pretrained("openai/clip-vit-base-patch32"),
    unet=UViTModel.from_pretrained("thu-ml/unidiffuser/unet"),
    vae=AutoencoderKL.from_pretrained("CompVis/stable-diffusion-v1-4/vae"),
    scheduler=None,
)

url = "https://bj.bcebos.com/v1/paddlenlp/models/community/thu-ml/data/space.jpg"
image = load_image(url)
image = pipe(image=image, generator=generator).images[0]
image.save("./unidiffuser-i2t2i.png")
