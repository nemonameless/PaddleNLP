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

from ppdiffusers import UniDiffuserPipeline
from ppdiffusers.utils import load_image

pipe = UniDiffuserPipeline.from_pretrained("thu-ml/unidiffuser")
image = load_image("https://bj.bcebos.com/v1/paddlenlp/models/community/thu-ml/data/space.jpg")
result = pipe(mode="i2t", image=image, prompt=None)
text = result.texts[0]
with open("image_to_text_generation-unidiffuser-result.txt", "w") as f:
    print("{}\n".format(text), file=f)
