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

from typing import Optional

import numpy as np
import paddle
from paddle import nn
from paddle.nn import functional as F

from paddlenlp.transformers import GPTConfig, GPTLMHeadModel, GPTTokenizer

from ..configuration_utils import ConfigMixin, register_to_config
from .modeling_utils import ModelMixin


class CaptionDecoder(ModelMixin, ConfigMixin):
    @register_to_config
    def __init__(
        self,
        prefix_length: int = 77,
        hidden_dim: int = 64,
        use_beam_search: bool = True,
    ):
        super(CaptionDecoder, self).__init__()
        self.prefix_length = prefix_length
        eos = "<|EOS|>"
        special_tokens_dict = {"eos_token": eos}
        self.tokenizer = GPTTokenizer.from_pretrained("gpt2-en")
        self.tokenizer.add_special_tokens(special_tokens_dict)
        config = GPTConfig.from_pretrained(
            "gpt2-en", vocab_size=len(self.tokenizer), eos_token_id=self.tokenizer.eos_token_id
        )
        self.gpt = GPTLMHeadModel(config)

        self.hidden_dim = hidden_dim
        self.encode_prefix = nn.Linear(768, hidden_dim) if hidden_dim is not None else nn.Identity()
        self.decode_prefix = nn.Linear(hidden_dim, 768) if hidden_dim is not None else nn.Identity()
        self.use_beam_search = use_beam_search

    def get_dummy_token(self, batch_size: int) -> paddle.Tensor:
        return paddle.zeros([batch_size, self.prefix_length], dtype=paddle.int64)

    def forward(
        self,
        tokens: paddle.Tensor,
        prefix: paddle.Tensor,
        mask: Optional[paddle.Tensor] = None,
        labels: Optional[paddle.Tensor] = None,
    ):
        embedding_text = self.gpt.gpt.embeddings.word_embeddings(tokens)
        hidden = self.encode_prefix(prefix)
        prefix = self.decode_prefix(hidden)
        embedding_cat = paddle.concat((prefix, embedding_text), axis=1)

        if labels is not None:
            dummy_token = self.get_dummy_token(tokens.shape[0])
            labels = paddle.concat((dummy_token, tokens), axis=1)
        out = self.gpt(inputs_embeds=embedding_cat, labels=labels, attention_mask=mask)

        if self.hidden_dim:
            return out, hidden
        else:
            return out

    @paddle.no_grad()
    def generate_captions(self, features):
        # the low dimension representation of clip feature
        features = paddle.split(features, 1, axis=0)
        generated_captions = []
        for feature in features:
            feature = self.decode_prefix(feature)  # back to the clip feature
            if self.use_beam_search:
                generated_captions.append(self.generate_beam(embedding=feature)[0])
            else:
                generated_captions.append(self.generate2(embedding=feature))
        return generated_captions

    @paddle.no_grad()
    def generate_beam(
        self,
        prompt=None,
        embedding=None,
        beam_size: int = 5,
        entry_length: int = 67,  # maximum number of words
        temperature: float = 1.0,
        stop_token: str = "<|EOS|>",
    ):
        stop_token_index = self.tokenizer.encode(stop_token)["input_ids"][0]
        tokens = None
        scores = None
        seq_lengths = paddle.ones([beam_size])
        is_stopped = paddle.zeros([beam_size], dtype=paddle.bool)

        if embedding is not None:
            generated = embedding
        else:
            if tokens is None:
                tokens = paddle.to_tensor(self.tokenizer.encode(prompt)["input_ids"])
                tokens = tokens.unsqueeze(0)
                generated = self.gpt.gpt.embeddings.word_embeddings(tokens)

        for i in range(entry_length):
            logits = self.gpt(inputs_embeds=generated)
            logits = logits[:, -1, :] / (temperature if temperature > 0 else 1.0)
            logits = F.softmax(logits, axis=-1).log()
            if scores is None:
                scores, next_tokens = logits.topk(beam_size, -1)
                generated = generated.expand([beam_size, *generated.shape[1:]])
                next_tokens, scores = next_tokens.transpose([1, 0]), scores.squeeze(0)
                if tokens is None:
                    tokens = next_tokens
                else:
                    tokens = tokens.expand([beam_size, *tokens.shape[1:]])
                    tokens = paddle.concat((tokens, next_tokens), axis=1)
            else:
                # TODO: nf
                mask = paddle.cast(is_stopped, "int32")
                logits[mask] = -float(np.inf)
                logits[mask, 0] = 0
                scores_sum = scores[:, None] + logits
                incerse_mask = ~is_stopped
                incerse_mask = paddle.cast(incerse_mask, "int32")
                seq_lengths[incerse_mask] += 1

                # logits[is_stopped] = -float(np.inf)
                # logits[is_stopped, 0] = 0
                # scores_sum = scores[:, None] + logits
                # seq_lengths[~is_stopped] += 1
                scores_sum_average = scores_sum / seq_lengths[:, None]
                scores_sum_average, next_tokens = scores_sum_average.reshape([-1]).topk(beam_size, -1)
                next_tokens_source = next_tokens // scores_sum.shape[1]
                seq_lengths = seq_lengths[next_tokens_source]
                next_tokens = next_tokens % scores_sum.shape[1]
                next_tokens = next_tokens.unsqueeze(1)
                tokens = tokens[next_tokens_source]
                tokens = paddle.concat((tokens, next_tokens), axis=1)
                generated = generated[next_tokens_source]
                scores = scores_sum_average * seq_lengths
                is_stopped = paddle.cast(is_stopped, "int32")  # TODO: nf
                is_stopped = is_stopped[next_tokens_source]
                is_stopped = paddle.cast(is_stopped, "bool")

            next_token_embed = self.gpt.gpt.embeddings.word_embeddings(next_tokens.squeeze()).reshape(
                [generated.shape[0], 1, -1]
            )
            generated = paddle.concat((generated, next_token_embed), axis=1)
            is_stopped = paddle.bitwise_or(is_stopped, next_tokens.equal(stop_token_index).squeeze())
            if is_stopped.all():
                break

        scores = scores / seq_lengths
        output_list = tokens.cpu().numpy()
        output_texts = [
            self.tokenizer.decode(output[: int(length)], skip_special_tokens=True)
            for output, length in zip(output_list, seq_lengths)
        ]
        order = scores.argsort(descending=True)
        output_texts = [output_texts[i] for i in order]
        return output_texts

    @paddle.no_grad()
    def generate2(
        self,
        tokens=None,
        prompt=None,
        embedding=None,
        entry_count: int = 1,
        entry_length: int = 67,  # maximum number of words
        top_p: float = 0.8,
        temperature: float = 1.0,
        stop_token: str = "<|EOS|>",
    ):
        generated_list = []
        stop_token_index = self.tokenizer.encode(stop_token)["input_ids"][0]
        filter_value = -float("Inf")

        for i in range(entry_count):
            if embedding is not None:
                generated = embedding
            else:
                if tokens is None:
                    tokens = paddle.to_tensor(self.tokenizer.encode(prompt))
                    tokens = tokens.unsqueeze(0)
                generated = self.gpt.gpt.embeddings.word_embeddings(tokens)

            for entry_idx in range(entry_length):
                logits = self.gpt(inputs_embeds=generated)
                logits = logits[:, -1, :] / (temperature if temperature > 0 else 1.0)
                sorted_logits = paddle.sort(logits, descending=True)
                sorted_indices = paddle.argsort(logits, descending=True)
                cumulative_probs = paddle.cumsum(F.softmax(sorted_logits, axis=-1), axis=-1)
                sorted_indices_to_remove = cumulative_probs > top_p
                sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
                sorted_indices_to_remove[..., 0] = 0

                indices_to_remove = sorted_indices[sorted_indices_to_remove]
                logits[:, indices_to_remove] = filter_value
                next_token = paddle.argmax(logits, -1).unsqueeze(0)
                next_token_embed = self.gpt.gpt.embeddings.word_embeddings(next_token)
                if tokens is None:
                    tokens = next_token
                else:
                    tokens = paddle.concat((tokens, next_token), axis=1)
                generated = paddle.concat((generated, next_token_embed), axis=1)
                if stop_token_index == next_token.item():
                    break

            output_list = list(tokens.squeeze().cpu().numpy())
            output_text = self.tokenizer.decode(output_list)
            generated_list.append(output_text)

        return generated_list[0]
