# তাযকিয়া ডাউনলোডার

ইউটিউবের একটি ভিডিও বা পুরো প্লেলিস্ট এক ক্লিকে কম্পিউটারে ডাউনলোড করার ছোট্ট ডেস্কটপ অ্যাপ (Windows ও macOS)। ভেতরে [yt-dlp](https://github.com/yt-dlp/yt-dlp) কাজ করে, ওপরে বাংলা ইন্টারফেস।

- ভিডিও, প্লেলিস্ট, শর্টস বা চ্যানেলের লিংক দিলেই তালিকা দেখায়; কোনগুলো লাগবে টিক দিয়ে বেছে নেওয়া যায়
- ভিডিও (সবচেয়ে ভালো / 1080p / 720p / 480p / 360p, MP4) অথবা শুধু অডিও (MP3 বা M4A)
- প্লেলিস্ট তার নিজের নামে আলাদা ফোল্ডারে, ক্রমিক নম্বরসহ (`001 - শিরোনাম.mp4`) সেভ হয়
- প্রতিটি ফাইলের অগ্রগতি, গতি ও বাকি সময়; মাঝপথে একটা বাদ দেওয়া বা সব বাতিল করা যায়, ব্যর্থগুলো আবার চেষ্টা করা যায়
- আগে ডাউনলোড হওয়া ফাইল আবার ডাউনলোড হয় না; থেমে যাওয়া ডাউনলোড যেখানে থেমেছিল সেখান থেকে চলে

> শুধু ব্যক্তিগত ব্যবহারের জন্য। ইউটিউব থেকে ডাউনলোড ইউটিউবের শর্তের বাইরে; ভিডিওর স্বত্ব সংশ্লিষ্ট নির্মাতাদের।

## Windows-এ ইনস্টল

1. [Releases](../../releases/latest) পাতা থেকে `TazkiyahDownloader-Setup-<ভার্সন>.exe` ডাউনলোড করুন।
2. চালান। Windows "Windows protected your PC" দেখালে **More info → Run anyway** চাপুন (অ্যাপটি সাইন করা নয়, তাই এটা আসে)।
3. Next → Install। স্টার্ট মেনু ও ডেস্কটপে **Tazkiyah Downloader** পাবেন। অ্যাডমিন পাসওয়ার্ড লাগে না।

ইনস্টল ছাড়া চালাতে চাইলে `…-portable.zip` খুলে `TazkiyahDownloader.exe` চালান। ffmpeg আর deno অ্যাপের ভেতরেই আছে, আলাদা কিছু লাগবে না। Windows 10/11-এ থাকা Microsoft Edge WebView2 দিয়ে উইন্ডো চলে।

## ব্যবহার

1. ইউটিউবে ভিডিও বা প্লেলিস্ট খুলে লিংক কপি করুন।
2. অ্যাপের ওপরের ঘরে পেস্ট করুন (পেস্ট করলেই নিজে খোঁজে)।
3. ভিডিও না শুধু অডিও, মান আর ফোল্ডার ঠিক করে **ডাউনলোড শুরু করুন**। ফাইল যায় `Downloads\Tazkiyah`-এ (বদলানো যায়)।

**"ইউটিউব সাময়িকভাবে আটকে দিয়েছে" দেখালে:** অ্যাপ নিজেই কিছুক্ষণ থেমে দুবার আবার চেষ্টা করে। তাও না হলে ডাউনলোড অপশনের "ইউটিউব bot বলে আটকালে" থেকে যে ব্রাউজারে ইউটিউবে লগইন করা আছে সেটি বেছে নিন (Windows-এ Firefox সবচেয়ে ভালো কাজ করে; Chrome/Edge খোলা থাকলে তাদের কুকি পড়া যায় না, বন্ধ করে চেষ্টা করুন)।

**হঠাৎ কোনো ভিডিওই ডাউনলোড না হলে:** ইউটিউব প্রায়ই বদলায়, তখন yt-dlp-এর নতুন ভার্সন লাগে। নতুন রিলিজ বানালেই (নিচে দেখুন) সর্বশেষ yt-dlp চলে আসে।

## নতুন ভার্সন বানানো

Windows ইনস্টলার GitHub Actions-এ তৈরি হয় ([`.github/workflows/build.yml`](.github/workflows/build.yml)):

```bash
git tag v1.0.1 && git push origin v1.0.1
```

ট্যাগ push করলে Windows মেশিনে অ্যাপ বিল্ড হয়, ffmpeg ও deno ভেতরে ঢোকে, তৈরি অ্যাপ দিয়ে একটা আসল ডাউনলোড পরীক্ষা হয়, তারপর Inno Setup ইনস্টলার আর portable zip Release-এ যুক্ত হয়। ট্যাগ ছাড়া পরীক্ষামূলক বিল্ড চাইলে Actions → Build → Run workflow; ফাইল পাবেন রানের Artifacts-এ।

## নিজের কম্পিউটারে চালানো (ডেভেলপমেন্ট)

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements-build.txt
.venv/bin/python app.py
```

macOS-এ ffmpeg লাগবে (`brew install ffmpeg`), না থাকলে ভিডিও শুধু 360p আর অডিও শুধু M4A হয়। macOS অ্যাপ বানাতে: `.venv/bin/pyinstaller --noconfirm tazkiyah-downloader.spec` → `dist/Tazkiyah Downloader.app`।

বিল্ড হওয়া অ্যাপ ঠিক আছে কি না (উইন্ডো ছাড়া) যাচাই:

```bash
"dist/Tazkiyah Downloader.app/Contents/MacOS/TazkiyahDownloader" --selftest "https://youtu.be/3bd5Ynr4Vv8" /tmp/selftest
```

| ফাইল | কাজ |
| --- | --- |
| `downloader.py` | লিংক চেনা, প্লেলিস্টের তালিকা, yt-dlp দিয়ে একে একে ডাউনলোড, অগ্রগতি |
| `app.py` | ডেস্কটপ উইন্ডো (pywebview), সেটিংস, ফোল্ডার বাছাই |
| `ui/index.html` | পুরো ইন্টারফেস |
| `tazkiyah-downloader.spec`, `installer.iss` | PyInstaller ও Inno Setup বিল্ড |

ফন্টগুলো SIL OFL 1.1 ([`ui/fonts/OFL.txt`](ui/fonts/OFL.txt))।
