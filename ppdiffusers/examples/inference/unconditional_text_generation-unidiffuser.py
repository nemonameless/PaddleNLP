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

from ppdiffusers import UniDiffuserTextGenerationPipeline
from ppdiffusers.models import UViTModel
from ppdiffusers.pipelines.unidiffuser import CaptionDecoder

generator = paddle.Generator().manual_seed(0)

pipe = UniDiffuserTextGenerationPipeline(
    unet=UViTModel.from_pretrained("thu-ml/unidiffuser/unet"),
    caption_decoder=CaptionDecoder.from_pretrained("thu-ml/unidiffuser/caption_decoder"),
    scheduler=None,
)

text = pipe(generator=generator).texts[0]
print(text)
with open("./unidiffuser-t.txt", "w") as f:
    print("{}\n".format(text), file=f)
