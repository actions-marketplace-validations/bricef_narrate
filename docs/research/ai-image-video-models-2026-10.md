# Five-cent stills and dollar clips reshape narrate's plans

> **Research for [#41](https://github.com/bricef/narrate/issues/41) and [#42](https://github.com/bricef/narrate/issues/42), 13 October 2026.** Models, prices and leaderboards in this field change monthly: re-check any figure before relying on it.

As of 13 October 2026, closed models lead both image and video generation. OpenAI's GPT Image 2.5 tops the Artificial Analysis image boards (Elo 1199). For video, Alibaba Wan 3.0, ByteDance Seedance 2.5, MiniMax H3, Black Forest Labs' FLUX 3 and Google's Gemini Omni Flash 1.1 lead, while Veo 3.1, Kling 3.0 and Runway Gen-4.5 have slid to mid-table. **OpenAI's Sora API shut down on 24 September 2026 with no replacement.** Among the image leaders, price matters more than quality. Google's Nano Banana 2.1 sits 13 Elo below GPT Image 2 (high) and costs about **5 cents for a native 16:9 2K frame**, roughly a third of GPT Image 2's high-quality price. 1080p video costs from **$0.05/s (silent Veo 3.1 Lite) to $0.57/s (Seedance 2.5)**, so one 8-second shot costs $0.40–4.55; most strong models charge $0.10–0.17/s. Open weights trail the closed leaders, and their licences are a trap: **the strongest open video model, MiniMax H3, is not licensed for use in the US, EU, UK or South Korea. Tencent's Hunyuan models exclude the EU, UK and South Korea, and the top three open image models forbid commercial use of their weights.** The licence-clean open choices are LTX-2.5 and Wan 2.2 for video, and Z-Image-Turbo, Qwen-Image-2512 and HiDream-O1 for images. None of them is practical on a CPU. For narrate, build the `google` provider first. One Gemini key covers Nano Banana 2.1 stills for `render:ai-img` ([#41](https://github.com/bricef/narrate/issues/41)) and Gemini Omni Flash 1.1 clips for `render:ai-vid` ([#42](https://github.com/bricef/narrate/issues/42)), at about $1.22 per 8-second 1080p shot, with Veo 3.1 Lite as the budget video model. Add fal second, for breadth, and an OpenAI-compatible images provider third, as the quality ceiling and the route to self-hosted servers. The issues' example models (gpt-image-1, imagen-4, veo-3, Sora) are now legacy or gone. Keep every price in dated data rather than code, because several current prices are promotional, pre-release or contradicted by another source.

## GPT Image 2.5 leads stills, but near-top quality now costs a nickel

On Artificial Analysis's blind-preference text-to-image board (AA-Image-T2I v2.0, read 13 October 2026), **OpenAI holds the top three places**: GPT Image 2.5 Sunburst at "max" quality (1199), GPT Image 2.5 Flare (1192) and GPT Image 2 at high quality (1172). Next, within overlapping confidence intervals, come **Google's Nano Banana 2.1 (1159), xAI's Grok Imagine Image 2.0 (1155) and Microsoft's MAI-Image-2.6 (1152)**, then Nano Banana 2 (1125), Meta's Muse Image and BFL's FLUX 3 Image (both 1115) ([AA text-to-image](https://artificialanalysis.ai/image/leaderboard/text-to-image)). The editing board has the same shape: Sunburst at 1186, and MAI-Image-2.6, Nano Banana 2.1 and Muse Image between 1123 and 1143 ([AA editing](https://artificialanalysis.ai/image/leaderboard/editing)).

Two caveats limit how much weight fine rankings deserve. First, AA blends its own panel with public Arena votes cast before 1 January 2026. Second, the live Arena board (arena.ai, formerly LMArena) refused automated reads. The newest Arena evidence is therefore a July mirror that puts GPT Image 2 first ([DataLearner mirror](https://www.datalearner.com/en/leaderboards/external/text-to-image)) and Microsoft's claim that MAI-Image-2.6 launched at No. 2 there ([Microsoft AI](https://microsoft.ai/news/pushing-the-quality-cost-frontier-with-mai-image-2-6/)).

The important pattern is that **less than 90 Elo separates the top eight, while their prices differ about twentyfold**. GPT Image 2.5 at max costs about $0.21 per 1024² image, against $0.034 for Nano Banana 2.1, about $0.039 for MAI-Image-2.6 and $0.01 for Muse Image ([AA text-to-image](https://artificialanalysis.ai/image/leaderboard/text-to-image); [RuntimeWire](https://runtimewire.com/article/meta-ships-muse-image-api-at-one-cent-per-image)). Several familiar names have fallen away. Google's docs now call Imagen "legacy … (shut down)", and the original Nano Banana (gemini-2.5-flash-image) was scheduled to shut down on 2 October 2026 ([Gemini image docs](https://ai.google.dev/gemini-api/docs/image-generation); [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)). Midjourney still has no official API, and its terms bar automated access ([MyArchitectAI](https://www.myarchitectai.com/blog/midjourney-apis)). Ideogram, Recraft, Firefly, Leonardo and Reve are missing from AA's top 25, although Ideogram (explicit seeds) and Recraft (vector output at $0.08) keep useful niches ([Recraft pricing](https://www.recraft.ai/docs/api-reference/pricing)).

| Model (vendor) | AA text-to-image Elo (rank) | AA edit Elo | Price for one ~1080p 16:9 still | Native 16:9 at ≥1080p | Notable |
|---|---|---|---|---|---|
| GPT Image 2.5 Sunburst / Flare, max (OpenAI) | 1199 / 1192 (1–2) | 1186 / 1167 | ~$0.21 at 1024²; 16:9 price only via OpenAI's calculator | Yes: custom sizes in multiples of 16 (1920×1088, 2048×1152) | Organisation verification required; Flare reportedly faster |
| GPT Image 2, high / medium / low (OpenAI) | 1172 (3) | 1129 | $0.165 / $0.041 / $0.005 at 1536×1024 | Yes (custom sizes) | Strong text rendering |
| Nano Banana 2.1 (Google) | 1159 (4–6) | 1141 | **$0.050 at 2K** ($0.025 batch); $0.034 at 1K | Yes, 16:9 at 1K/2K/4K | Up to 14 references (5 characters); SynthID always on; GA 6 Oct 2026 |
| Grok Imagine Image 2.0 (xAI) | 1155 (4–6) | 1113 | $0.04 per xAI; AA lists $0.06 | Not documented | — |
| MAI-Image-2.6 (Microsoft) | 1152 (4–6) | 1143 | ~$0.039 (AA estimate; no list price) | No, ≤1.5K | Foundry public preview |
| Muse Image (Meta) | 1115 (8–11) | 1123 | $0.01 | Sizes not found | Meta API, fal, OpenRouter |
| FLUX 3 Image (BFL) | 1115 (8–11) | — | $0.100 at 2k (~4 MP); $0.048 at 1k | Yes, 2k tier | Up to 10 references, layout control |
| Nano Banana Pro (Google) | 1104 (10–15) | 1105 | $0.134 | Yes | C2PA on Vertex |
| Seedream 5.0 Pro (ByteDance) | 1082 (16–17) | 1113 | ~$0.045 (third party) vs $0.09 (AA) | Covers 2.07 MP | Prices conflict |
| Recraft V4.1 | Not in top 25 | — | $0.035 raster, $0.08 vector | — | Vector output; $0.004 upscale |
| Ideogram 3.0 / 4.x | Not in top 25 | — | ~$0.03–0.10 (third party) | No (1312×736) | Documents an integer seed |

Sources for the table: [OpenAI image guide](https://developers.openai.com/api/docs/guides/image-generation), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [xAI models](https://docs.x.ai/docs/models), [BFL pricing](https://docs.bfl.ai/quick_start/pricing), [Atlas Cloud on Seedream](https://www.atlascloud.ai/blog/ai-updates/seedream-5-0-pro-price), [Ideogram API](https://developer.ideogram.ai/api-reference/api-reference/generate-v3), and the AA boards above.

**Three families produce native 16:9 at or above 1080p:**

- **OpenAI's gpt-image-2 and 2.5.** They take custom sizes whose edges are multiples of 16, up to 3840 px. That makes 1920×1080 invalid, so the request is 1920×1088 or 2048×1152 ([OpenAI image guide](https://developers.openai.com/api/docs/guides/image-generation)).
- **Google's Nano Banana family.** It offers 16:9 at 1K, 2K and 4K tiers of about 1, 4 and 16 MP ([Vertex: Gemini 3 Pro Image](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-pro-image)). The exact pixel sizes were not verified.
- **BFL's FLUX 3 Image** at its 2k tier.

Other leaders need an upscale: MAI-Image-2.6 stops at 1.5K, Nano Banana 2 Lite at 1K, and Ideogram 3.0's nearest 16:9 size is 1312×736.

Reference control is good across the top tier. Nano Banana 2.1 takes up to 14 references, including 5 characters, which is the main tool for keeping a character consistent across a video's pictures ([Gemini image docs](https://ai.google.dev/gemini-api/docs/image-generation)). Seeds are a different matter. **Of the hosted vendors checked, only Ideogram documents an integer seed**; the OpenAI and Gemini docs read do not mention one.

**Google embeds a SynthID watermark in every Gemini image**, and Vertex lists C2PA Content Credentials for Nano Banana Pro. OpenAI's C2PA status was not confirmed. OpenAI also requires organisation verification before any GPT Image call, and complex prompts can take up to two minutes.

For a typical explainer with 20–40 stills, the image bill is:

- **$0.20–0.40** with Muse Image or Gemini batch pricing. Batch pricing allows up to 24 hours of turnaround.
- **$1–2** with Nano Banana 2.1 at 2K.
- **$4–10** with GPT Image 2 or 2.5 at high or max quality.

The GPT figure is an extrapolation. OpenAI gives 16:9 costs only through an interactive calculator, and its 1024² high price ($0.211) is higher than its 1536×1024 price ($0.165), so cost does not scale with area.

## Video leadership changed hands as Sora left and Veo slid to mid-table

OpenAI removed Sora 2 and Sora 2 Pro from its API on **24 September 2026**. It says there is "no one-to-one replacement", and its pricing page now lists no video model ([OpenAI deprecations](https://developers.openai.com/api/docs/deprecations); [OpenAI video guide](https://developers.openai.com/api/docs/guides/video-generation)).

On AA's text-to-video board with audio, **Wan 3.0 leads at 1158**. Close behind, within overlapping intervals, are Utopai X (1149, no API), Seedance 2.5 (1144), MiniMax H3 (1141, open weights), H3 Max (1134) and FLUX 3 (1131). Gemini Omni Flash 1.1 is 7th–8th at 1115 ([AA text-to-video](https://artificialanalysis.ai/video/leaderboard/text-to-video)). Image-to-video is the mode narrate's `image:` setting would use. There, **MiniMax H3 (1131), Vidu Q4 Preview and Gemini Omni Flash 1.1 (both 1130) tie for first** ([AA image-to-video](https://artificialanalysis.ai/video/leaderboard/image-to-video)).

The former leaders have slipped:

- **Kling 3.0 Pro** is now the board's fixed 1000 anchor.
- **Veo 3.1** ranks 19th–21st on text-to-video (965) and 13th on image-to-video (1034).
- **Runway Gen-4.5**, which is silent and 720p only, ranks 24th on the silent board (925). AA could test it only on the 61% of prompts that fit its 1,000-character limit.

Google itself now calls Omni "the recommended default for video generation". It keeps Veo for scene extension, last-frame control and legacy pipelines ([Gemini video overview](https://ai.google.dev/gemini-api/docs/video)).

| Model | AA text-to-video Elo (rank) | AA image-to-video Elo | 1080p $/s, silent / with audio | One 8 s 1080p clip | Length per call | Frames and references | Access and job model |
|---|---|---|---|---|---|---|---|
| Wan 3.0 (Alibaba) | 1158 (1–2) | 1118 | — / $0.20 (Singapore promo; $0.165 Global) | $1.60 | Up to 30 s* | Image-to-video | Model Studio, Runway; async |
| Seedance 2.5 (ByteDance) | 1144 (2–4) | 1125 | Audio always / $0.569 | $4.55 | 4–30 s | First/last frame, up to 50 references, 480p draft mode | BytePlus ModelArk (billed in tokens), Runway |
| MiniMax H3 | 1141 (3–5) | **1131 (1)** | No 1080p tier: 768p $0.08, 2K $0.13 | $1.04 at 2K | 4–15 s | First/last frame; 9 images, 3 videos, 3 audio clips | MiniMax API, poll every 10 s; open weights |
| FLUX 3 Video (BFL) | 1131 (5–6) | 1084 | Audio included / $0.29 (upscaled); draft $0.06 | $2.32 | Up to 20 s* | Image-to-video | BFL API |
| **Gemini Omni Flash 1.1 (Google)** | 1115 (7–8) | **1130 (1–5)** | Audio always / **$0.152** (upscaled) | **$1.22** | 3–10 s; extends to 40 s | First/last frame, subject references, up to 3 reference videos; no seed or negative prompt | Gemini API, Vertex, Runway; synchronous, URI for files over 4 MB |
| Grok Imagine Video 1.5 (xAI) | 1047 (11–12) | 1065 | ? / $0.25 (units inferred) | $2.00 | Up to 15 s | 14 references; pins first/mid/last frames | xAI API, poll |
| Kling 3.0 (Kuaishou) | 1000 (anchor) | 1000 | **$0.112** / $0.168 | $0.90 silent | Up to 15 s* | Image-to-video; Omni takes video input; multi-shot | kling.ai, fal; `callback_url`* |
| Veo 3.1 (Google) | 965 (19–21) | 1034 | $0.20 (Vertex) / $0.40 | $1.60 / $3.20 | 4, 6, 8 s; **1080p requires 8 s** | First/last frame, 3 references | Gemini API, Vertex, Runway, fal, Replicate; long-running operation |
| Veo 3.1 Fast | 960 (19–21) | 1017 | $0.10 / $0.12 | $0.80 / $0.96 | As Veo 3.1 | As Veo 3.1 | As Veo 3.1 |
| **Veo 3.1 Lite** | 946 (22–25) | — | **$0.05** (Vertex) / $0.08 | **$0.40 / $0.64** | 8 s at 1080p; no extension | First/last frame; no references | Gemini API, Vertex |
| Runway Gen-4.5 | 925 (silent board) | — | $0.12, 720p only, silent | $0.96 at 720p | 2–10 s | First frame only | Runway API, poll no faster than every 5 s |
| Luma Ray3.2 | Not ranked | — | $0.24–0.36 (pre-release prices) | $3.60 (billed as 10 s) | 5 or 10 s | Up to 64 keyframes; HDR/EXR | Luma API, poll |
| Vidu Q4 Preview | — | 1130 (1–5) | ~$0.084 (AA, image-to-video) | ~$0.67 | 3–16 s | Image- and reference-to-video | Vidu API (credits priced in RMB) |
| LTX-2.5 Fast (open weights) | 948 (22–25) | 997 | Hosted $0.13 ($7.80/min) | $1.04 | Up to 20 s* | Image-to-video, keyframes, multishot | fal, Runware, or self-hosted |

\* Third-party source only. Not available programmatically: Sora 2 (shut down), Utopai X (no API), Midjourney video (no official API), Adobe Firefly Video (enterprise contract only) and Moonvalley Marey (no public API pricing).

Sources for the table: [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Vertex pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing), [Veo docs](https://ai.google.dev/gemini-api/docs/veo), [Omni docs](https://ai.google.dev/gemini-api/docs/omni), [Kling pricing](https://kling.ai/dev/pricing), [MiniMax pricing](https://platform.minimax.io/docs/guides/pricing-paygo.md), [BytePlus pricing](https://docs.byteplus.com/en/docs/modelark/model-pricing), [Alibaba pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing), [Runway pricing](https://docs.dev.runwayml.com/guides/pricing/), [Luma pricing](https://docs.agents.lumalabs.ai/guides/pricing/), [BFL pricing](https://docs.bfl.ai/quick_start/pricing), [xAI models](https://docs.x.ai/docs/models), [Unifically on Midjourney](https://unifically.com/blogs/midjourney-api), [Adobe Community](https://community.adobe.com/questions-404/does-adobe-firefly-ai-supports-text-to-video-api-calls-1639384).

**Silent output is not always cheaper, which matters for narrated video.** Only some routes charge less for silence:

- Veo on Vertex AI, or Veo through Runway or fal with audio off.
- Kling.
- Seedance 1.5 Pro.
- Alibaba's wan2.6-flash.

Gemini Omni, every Seedance 2.x model and Veo through the Gemini API all bill for audio that narrate would then mute. On Veo 3.1 Lite at 1080p, the Gemini API's audio-on rate ($0.08/s) is 60% above Vertex's silent rate ($0.05/s) ([Vertex pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)). Omni documents no way to switch audio off ([Omni docs](https://ai.google.dev/gemini-api/docs/omni)).

Clip length and resolution are linked in ways a provider adapter has to model. **Veo 3.1 offers 1080p and 4K only for 8-second clips**; 4- and 6-second clips are 720p. That means a 5-second 1080p shot on Veo costs the same as an 8-second one ([Veo docs](https://ai.google.dev/gemini-api/docs/veo)). The other models differ:

| Model | Lengths | Resolution limits |
|---|---|---|
| Omni | 3–10 s | 360p to 4K; 1080p and 4K are upscaled |
| Luma Ray3.2 | 5 or 10 s | — |
| MiniMax H3 | 4–15 s | 768p or 2K only, no 1080p tier |
| Seedance 2.5 | 4–30 s | — |

For longer shots, Veo extends in 7-second steps up to 148 s, but only at 720p. Omni extends to 40 s. Kling's multi-shot mode and LTX-2.5's native multishot join several shots in one call.

Reference control has become the main way to keep shots consistent:

- Veo takes first and last frames plus three reference images.
- Omni takes subject references and up to three 3-second reference videos.
- H3 takes 9 images, 3 videos and 3 audio clips.
- Seedance 2.5 takes up to 50 reference assets.
- Grok pins first, middle and last frames.
- Runway takes only a first frame.

Determinism is weak everywhere. **Veo accepts a seed but "does not guarantee determinism", and Omni has no seed or negative prompt at all.** No independent prompt-adherence benchmark for video turned up, so AA's preference Elo is the best available proxy.

**Every video API is asynchronous in practice**, and the details narrate has to handle differ by vendor:

- **Veo** returns a long-running operation that takes 11 seconds to 6 minutes. Google stores the output for only 2 days ([Veo docs](https://ai.google.dev/gemini-api/docs/veo)).
- **Runway** asks clients to poll no faster than every 5 seconds, queues throttled tasks, and expires output URLs within 24–48 hours ([Runway API](https://docs.dev.runwayml.com/api.md)).
- **Luma** suggests waiting 30 seconds before the first poll and timing out at 10 minutes.
- **MiniMax** recommends polling every 10 seconds and documents no webhook ([MiniMax guide](https://platform.minimax.io/docs/guides/video-generation.md)).
- **Omni** is the exception: it returns synchronously, except for files over 4 MB, which come back as a URI.

Google, BytePlus and Alibaba bill only successful generations. **Watermarking is confirmed only for Google, which applies SynthID to Veo and Omni output.** Seedance requests carry a `watermark` flag, set to true in the official examples. Regional limits also apply:

- In the EU, UK, Switzerland and MENA, Veo allows only adult person generation ([Veo docs](https://ai.google.dev/gemini-api/docs/veo)).
- Omni's editing and extension of uploaded videos is unavailable in the EEA, Switzerland and the UK ([Omni docs](https://ai.google.dev/gemini-api/docs/omni)).

## The best open weights exclude the UK, EU or US, or forbid commercial use

Open weights trail the closed leaders by a wide margin in images and a narrow one in video. **Qwen-Image-2.1 is the top open image model at 1037**, about 160 Elo below GPT Image 2.5 ([AA open-weights board](https://artificialanalysis.ai/image/leaderboard/text-to-image?open-weights=true)). **MiniMax H3 is the only open video model in the top tier**: 3rd–5th on text-to-video and tied first on image-to-video. After it come MAGI-2 Preview (image-to-video 1044) and LTX-2.5 (text-to-video 948).

Alibaba's newer Wan models (2.5 to 3.0) are API-only, despite websites claiming otherwise. Its Hugging Face organisation lists only Wan 2.1 and 2.2 ([HF Wan-AI](https://huggingface.co/api/models?author=Wan-AI&sort=createdAt&direction=-1&limit=40)). The open leaderboard has also churned repeatedly: FLUX.2 [dev] led in April, Ideogram 4.0 from about June to August, and Qwen-Image-2.1 since late September ([Magic Hour export](https://magichour.ai/model-leaderboard/image-generation); [AA open-weights board](https://artificialanalysis.ai/image/leaderboard/text-to-image?open-weights=true)).

Licences, not quality, decide which of these narrate can recommend:

| Model | Kind | AA Elo | Weights licence | Commercial use | **Territory exclusions** | Hardware |
|---|---|---|---|---|---|---|
| MiniMax H3 | Video | Text-to-video 1141, image-to-video 1131 | MiniMax H3 Community | Yes; written authorisation above $20M revenue; must display the name | **United States, EU, UK, South Korea** | 33B plus 32B encoder; RTX 5090 at NVFP4 with ≥200 GiB host RAM |
| HunyuanVideo 1.5 | Video | Not on current board | Tencent Hunyuan Community | Under 100M monthly users | **EU, UK, South Korea** | 8.3B; ≥14 GB with offload |
| HunyuanImage 3.0 | Image | 995 (Instruct) | Tencent Hunyuan Community | Under 100M monthly users | **EU, UK, South Korea** | ≥3×80 GB |
| Qwen-Image-2.1 | Image | 1037 (top open) | Qwen Research | **No**: research or evaluation only | None noted | 7B; FP8 on 24 GB |
| Ideogram 4.0 | Image | 1012 | Ideogram 4 Non-Commercial (gated) | **No** without a paid licence | None noted | 9.3B; nf4 on 24 GB |
| FLUX.2 [dev], [klein] 9B | Image | 1000, 940 | FLUX Non-Commercial | **No** for the model; outputs usable | None noted | 32B, ~32 GB at FP8 |
| LTX-2.5 | Video | Text-to-video 948, image-to-video 997 | LTX-2.x Community (gated) | Free under $10M entity revenue | None noted | 22B plus 12B encoder; 24–32 GB at int8/fp8 |
| MAGI-2 Preview | Video | Image-to-video 1044 | Apache 2.0 | Yes | None | 8 Hopper GPUs |
| Wan 2.2 | Video | Not on current board | Apache 2.0 | Yes | None | 5B on 24 GB; A14B ≥80 GB |
| HiDream-O1-Image | Image | 982 | MIT | Yes | None | 8B; VRAM unstated |
| Cosmos3-Super | Image | 995 / 987 | OpenMDW-1.1 | Yes | None | 64B; 8×H100 class |
| Z-Image-Turbo | Image | 941 | Apache 2.0 | Yes | None | 6B; 16 GB at BF16 |
| Qwen-Image-2512 | Image | Not found | Apache 2.0 | Yes | None | 20B |
| FLUX.2 [klein] 4B | Image | 862 | Apache 2.0 | Yes | None | 4B; ~13 GB |

Sources for the table: [MiniMax H3 licence](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE), [HunyuanVideo 1.5 licence](https://huggingface.co/tencent/HunyuanVideo-1.5/blob/main/LICENSE), [HunyuanImage 3.0 licence](https://huggingface.co/tencent/HunyuanImage-3.0/blob/main/LICENSE), [Qwen-Image-2.1 licence](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE), [Ideogram 4.0](https://huggingface.co/ideogram-ai/ideogram-4-fp8), [FLUX.2 [dev] licence](https://huggingface.co/black-forest-labs/FLUX.2-dev/blob/main/LICENSE.md), [FLUX.2 klein](https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence), [LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5), [MAGI-2](https://huggingface.co/sand-ai/MAGI-2-preview), [Wan 2.2](https://github.com/Wan-Video/Wan2.2), [HiDream-O1](https://github.com/HiDream-ai/HiDream-O1-Image), [Cosmos3-Super](https://huggingface.co/nvidia/Cosmos3-Super), [Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo), [Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512), [Nuvalab on running H3](https://nuvalab.ai/blog/run-minimax-h3-locally-gpu-vram-requirements/).

These territory clauses govern running the weights yourself. Calling the same model through MiniMax's own API or an aggregator falls under that service's terms, which this research did not check. **A tool that anyone can download cannot know where its user sits, so narrate's self-hosting guidance and any default open model must be legal everywhere.** That rules out H3, both Hunyuan models and the non-commercial weights.

FLUX.2 [dev] draws a subtler line. BFL claims no rights over outputs, but using the model for revenue-generating work is not covered, and the licence requires filtering or human review of outputs before distribution. The clean shortlist is LTX-2.5 and Wan 2.2 for video, and Z-Image-Turbo, Qwen-Image-2512 (strong slide and infographic text), HiDream-O1 and FLUX.2 [klein] 4B for images. Accepting a permissive licence costs 40–100 Elo: Qwen-Image-2.1 scores 1037, against 982 for HiDream-O1 (MIT) and 941 for Z-Image-Turbo (Apache 2.0).

Hardware is manageable for images but heavy for video. Measured image times:

- Z-Image-Turbo: about 2.3 s for a 1024² image on an RTX 4090, but it distorts when asked for 2K directly ([Thunder Compute](https://www.thundercompute.com/blog/z-image-turbo-comfyui)).
- Qwen-Image-2.1: 8.39 s at 1024² and 20 steps on an RTX 5090 ([Stable Yogi](https://stableyogi.com/blog/rtx-5090-qwen-image-2-1-power-limit-benchmark)).
- FLUX.2 [klein] 4B: 0.57 s on an H100 ([inferencebench](https://inferencebench.io/blog/flux2-klein-4b-image-generation-benchmark/)).

For video, LTX-2.5 is the best fit for a single card. It renders a native 1920×1088, and an RTX 5090 makes **a 4-second 720p clip in about 25 s and an 8-second one in about 3 minutes** ([runaihome](https://runaihome.com/blog/ltx-2-5-local-ai-video-hardware-guide-2026/)). H3 at NVFP4 takes 38.6 s per 5-second clip on an RTX 5090, but the recipe wants at least 200 GiB of host RAM. Wan 2.2's 5B model needs up to 9 minutes for a 5-second 720p clip ([Wan2.2](https://github.com/Wan-Video/Wan2.2)).

Step-distilled checkpoints, now the default, give 5–25× speed-ups at a known cost: slower motion. That suits slow explainer pans but not action shots ([Wan2.2-Lightning discussion](https://huggingface.co/lightx2v/Wan2.2-Lightning/discussions/26)).

**A CPU is not a viable host.** FLUX.1 [schnell], a 12B model, took about 270 s for a 512² image on a Core i7 ([FastSD CPU](https://github.com/rupeshs/fastsdcpu)). No CPU timings exist for current models; a 1080p frame from one of them would plausibly take over ten minutes, which is an extrapolation. No CPU video timing exists at all.

Self-hosting is cheap per unit and expensive in effort. At full use, Z-Image-Turbo costs about $0.0002–0.0006 per 1024² image on a rented RTX 4090, against $0.005 hosted. LTX-2.5 costs about $0.04–0.13 of GPU time per finished minute on an RTX 5090, against $7.80/min hosted. Allow for three takes per kept clip and 75% idle time, and self-hosting still comes out roughly 6–9× cheaper ([RunPod pricing](https://www.runpod.io/pricing)). Model loading, though, is tens of gigabytes (LTX-2.5's quick-start set is about 66 GiB), and per-second serverless GPUs bill that load time on every cold start. Two serverless options fit occasional use:

- **RunPod Serverless** bills by the second, about $1.10/h for an RTX 4090, with a 5-second idle default ([RunPod serverless](https://docs.runpod.io/serverless/pricing)).
- **Modal** bills by the second, about $3.95/h for an H100, with a 60-second idle default and $30 a month of free credit ([Modal pricing](https://modal.com/pricing)).

**For a few clips per build, hosted APIs are likely cheaper once engineering time counts.**

## Aggregators sell one key and breadth, not discounts

fal, Replicate, Together, Runware, WaveSpeed and OpenRouter all carry the current closed models alongside open ones. Their prices follow two patterns:

- **Google models sell at or near Google's own rates**, with markups from zero to about 12%. For example, Veo 3.1 with audio costs $0.40/s both on Google and on fal, and fal's silent Veo is $0.20/s, the same as Vertex ([fal Veo 3.1](https://fal.ai/models/fal-ai/veo3.1)).
- **ByteDance, Kling and MiniMax prices vary several-fold** between aggregators. A third party puts Seedance 2.5 at about $0.47/s at 720p on fal against $0.23/s direct ([ClipSpeed](https://www.clipspeed.ai/blog/veo-vs-seedance-vs-kling.html)). fal's Kling 3.0 Pro matches Kling's official $0.112/s silent rate ([fal Kling 3.0 Pro](https://fal.ai/models/fal-ai/kling-video/v3/pro/text-to-video)).

Runway also resells Veo, Wan 3.0, Seedance and MiniMax under one credit balance, with an audio-off switch for Veo and free "Model Routers" that pick a model by cost or quality ([Runway pricing](https://docs.dev.runwayml.com/guides/pricing/)).

**No common API standard exists, but every provider uses the same pattern**: submit a job, get an ID, poll or receive a webhook, then download. The main variants:

- **fal** wraps every model in one queue that you can poll or stream, with webhooks and cancellation, but each model keeps its own input schema ([fal queue](https://fal.ai/docs/model-apis/model-endpoints/queue)).
- **Replicate** waits synchronously for up to 60 seconds, then falls back to polling or webhooks, and accepts a `Cancel-After` deadline ([Replicate predictions](https://replicate.com/docs/topics/predictions/create-a-prediction)).
- **OpenRouter** normalises video into one asynchronous schema covering resolution, duration, audio, frames and references, but returns images only as base64 ([OpenRouter video](https://openrouter.ai/blog/announcements/video-generation/)).
- **Together** returns each video job's `cost` ([Together videos](https://docs.together.ai/docs/videos-overview)).
- **Runware** returns cost per task when asked, through `includeCost` ([Runware docs](https://runware.ai/docs/getting-started/introduction)).

The operational differences matter more than the prices:

- **Output lifetime.** Replicate deletes API outputs after **1 hour** ([Replicate retention](https://replicate.com/docs/topics/predictions/data-retention)). Runware keeps them 7 days, and fal lets each request set its own expiry.
- **Concurrency.** New fal accounts start at 2 concurrent requests and rise to 40 as credit is bought; requests over the limit are queued, not rejected ([fal concurrency](https://fal.ai/docs/documentation/model-apis/concurrency-limits)). WaveSpeed's default tier allows 2 concurrent requests and 5 per minute ([WaveSpeed docs](https://wavespeed.ai/docs)).
- **Credit expiry.** fal credits expire after 365 days.
- **Listing churn.** fal's main Veo 3.1 endpoint will be deprecated on **22 October 2026**. Together still lists Sora 2 and the shut-down Gemini 2.5 Flash Image ([Together pricing](https://www.together.ai/pricing)).
- **fal's terms** license use for personal or internal business purposes, with a separate licence for products built on the API. They forbid using third-party model outputs to train models or build competing products, and they keep request payloads for 30 days unless a header turns that off ([fal Terms](https://fal.ai/terms)).

No independent uptime data exists for any aggregator.

## What narrate should build: Google first, fal second, prices as data

The issues propose an OpenAI-compatible provider first, then Google, then fal. That order made sense when Sora and Imagen existed. Three orders now compete:

- **OpenAI-compatible first.** The protocol is the most reusable: one simple synchronous adapter reaches OpenAI's top-ranked image model, Together's catalogue and self-hosted servers such as SGLang Diffusion, which speaks the same API ([SGLang Diffusion](https://docs.sglang.io/diffusion/index.html)). But OpenAI no longer sells video, so this provider serves only #41. It also starts at three to four times the price of Nano Banana 2.1, and it requires organisation verification.
- **fal first.** It has the widest catalogue under one key and an asynchronous queue that suits both issues. But each model has its own schema, and endpoints are already being deprecated.
- **Google first. This is the pick.** One `GEMINI_API_KEY` covers both issues, which is exactly the shared configuration #42 asks for. It reaches a top-six image model at 5 cents, the top-tier image-to-video model (Omni), and the cheapest 1080p video (Veo 3.1 Lite).

So build Google first, fal second for breadth (Kling with audio off, MiniMax H3, LTX-2.5, licence-clean open image models, silent Veo), and the OpenAI-compatible images provider third, as the quality ceiling and the self-hosting route.

| Role | Provider and model | Cost | Why | Caveat |
|---|---|---|---|---|
| #41 default still | `google`, `gemini-nano-banana-2.1`, 2K 16:9 | $0.050 ($0.025 batch) | Elo 1159, native 16:9, 14 references | SynthID always on; one week old |
| #41 text-heavy or best quality | `openai`, `gpt-image-2.5-flare` at 2048×1152 | ~$0.17–0.21+ (extrapolated) | #1–2 on generation and editing | Needs organisation verification; 16:9 price only via calculator |
| #41 licence-clean open model | `fal`, Z-Image-Turbo | $0.005/MP | Apache 2.0, no GPU needed | Elo 941; distorts at 2K, so upscale |
| #41 self-hosted | OpenAI-compatible `base-url` to SGLang serving Z-Image-Turbo or Qwen-Image-2512 | Fractions of a cent of GPU time | Apache 2.0 | Needs a rented GPU |
| #42 default clip | `google`, `gemini-omni-1.1-flash`, 1080p | $0.152/s, **$1.22 per 8 s** | Top tier on image-to-video, any 3–10 s length | Audio billed and muted; no seed or negative prompt |
| #42 budget clip | `google`, `veo-3.1-lite-generate-preview`, 1080p | $0.64 per 8 s (Gemini API); $0.40 silent on Vertex | Cheapest 1080p | 1080p only at 8 s; Elo 946; preview model ID |
| #42 silent mid-tier | `fal`, Kling 3.0 Pro, audio off | $0.112/s, $0.90 per 8 s | Up to 15 s; silent pricing | Elo 1000 |
| #42 self-hosted | HTTP endpoint to LTX-2.5 on a rented RTX 5090 | ~$0.005–0.05 of GPU time per clip | Native 1920×1088; free under $10M revenue | Gated download; cold loads of ~66 GiB |

For scale, consider a three-minute explainer with 24 generated stills and six 8-second clips:

- **Default stack: about $8.50 per clean pass.** That is $1.21 for the stills and $7.30 for the clips. If each clip needs three attempts, an assumption rather than a measured rate, it comes to roughly $23.
- **Budget stack, with Veo 3.1 Lite: about $5.05 per clean pass.**

The research also changes several details of the two issues:

1. **Update the example names.** gpt-image-1 should become gpt-image-2, and imagen-4 should become Nano Banana 2.1. veo-3 IDs are deprecated in favour of veo-3.1 or Omni. Remove `openai` (Sora) from #42's provider list.
2. **Treat `seed` and `negative` as optional hints.** Record them in the sidecar and warn when a provider ignores them. Veo's seed is not deterministic, Omni has neither setting, and even diffusers does not guarantee identical output with an identical seed ([diffusers reproducibility](https://huggingface.co/docs/diffusers/main/en/using-diffusers/reusing_seeds)). **The `.narrate/generated/` cache is the real reproducibility mechanism, and it matters more than the issues assume.** Outputs expire within hours or days (Replicate after 1 hour, Veo after 2 days) and whole APIs vanish (Sora), so the project folder holds the only durable copy.
3. **Model each provider's lengths and resolutions in the duration rule.** "Nearest length at or above" also needs per-model resolution coupling: a 5-second 1080p Veo request is billed as 8 seconds, and H3 has no 1080p tier.
4. **Ask for silence where it is cheaper.** That means Kling, fal or Vertex Veo, and Runway. Accept the audio charge on Omni.
5. **State the spending guard in dollars, not just seconds.** Ten 8-second clips cost $4 on silent Veo Lite and $46 on Seedance 2.5. That spread also supports #42's proposal that a CI build without `--generate` should fail. Keep prices in a dated table, and prefer costs the provider reports (Together's `cost`, Runware's `includeCost`, BytePlus usage tokens, Gemini tokens) over computed ones.
6. **Save the job ID as soon as a job is submitted.** Vendors bill completed jobs, so an interrupted build that resubmits pays twice. A build that resumes polling the saved job does not.
7. **Make stills the first step toward clips.** Iterate on a key frame with #41 at 5 cents a try, using character references for consistency. Then animate it once through image-to-video, where Omni ties for first. This partly answers #41's open question on image inputs: bring references and first frames into this round.
8. **Treat a CPU `local` image provider as GPU-only or defer it.** On a CPU it would take minutes per frame at far below leaderboard quality, so the self-hosting path is the OpenAI-compatible endpoint on a rented GPU.

## Conclusion

The research turns narrate's question around: switching models matters more than picking the right one. The quality gaps among the top five image and video models are smaller than their price gaps and smaller than the leaderboard churn of the past six months. In that time OpenAI's video API vanished, Veo 3.1 slid to 19th, and the top open image model changed twice. A narrate provider layer with model IDs, durations, resolutions and dated prices in data, and thin adapters around the shared submit-poll-download pattern, will outlast any recommendation in this report. Google is the right first adapter because it is cheap and near the top for both media under one key, not because it leads either board.

Licensing is the second structural finding. Hosted APIs move the licence question into vendor terms that this research did not audit. Self-hosting raises it immediately, because the most attractive open video weights cannot legally run in the US, EU or UK. For an open tool, the safe default is to point users at hosted models first and to name only Apache-, MIT- or LTX-licensed weights for self-hosting. Open questions remain:

- Commercial-use terms and watermarking for vendors other than Google.
- Whether calling MiniMax H3 through an API from a territory its weights licence excludes is permitted.
- Exact 16:9 prices for GPT Image 2.5.
- Exact pixel sizes for Gemini's 2K 16:9 tier.

Check these before the provider list is final.
