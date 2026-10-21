---
size: 1080p
voice: Narrator
canvas: "#0b1020"
transition: crossfade 0.5
background: uplifting-2 0.1 fade-in fade-out
overlay: overlays/chapters.html
subtitles: external
transcript: true
poster-time: 4
---

<!-- How HTTPS works: a video explainer, written in narrate. Every picture is an animated HTML scene in
     scenes/, timed to the narration by marks; the chapter bar along the bottom is an overlay. -->

![](scenes/title.html)

(overlay: none)

Look at the address bar. <mark name="lock"/>That little padlock, and the <mark name="s"/>S at the end of HTTPS, mean a lot happened before this page even loaded.

In a split second, your browser and a stranger agreed on a secret, in public. And the stranger proved who it was.

---

![](scenes/postcard.html)

Without the S, plain HTTP sends everything just as it is. Your request passes through <mark name="cafe"/>the café's Wi-Fi, <mark name="isp"/>your internet provider, <mark name="net"/>and a chain of networks you'll never see.

<mark name="read"/>Any of them can read it, like a postcard. <mark name="change"/>And any of them could quietly change it on the way.

---

![](scenes/promises.html)

HTTPS makes three promises. <mark name="private"/>Nobody else can read what you send. <mark name="intact"/>Nobody can change it without being caught. <mark name="authentic"/>And the site at the other end really is the one you asked for.

---

![](scenes/tunnel.html)

Under the hood, HTTPS is plain HTTP, the same requests and the same pages, <mark name="tls"/>carried inside a protected tunnel called TLS, Transport Layer Security.

<mark name="one"/>To build the tunnel, both sides must agree on a secret key. <mark name="two"/>And your browser must check who's on the other end.

---

![](scenes/cipher.html)

First, the secret. <mark name="lock"/>With a shared key, encryption turns a message into noise. <mark name="unlock"/>The same key turns it back.

It's fast enough to protect every byte of every page. <mark name="catch"/>But if you send the key across the network, <mark name="copy"/>anyone listening gets a copy.

So how can two strangers agree on a key, in public?

---

![](scenes/paint.html)

With a key exchange. Picture it with paint.

<mark name="public"/>Both sides start with the same colour, out in the open. <mark name="secret"/>Each one adds a secret colour of its own.

<mark name="swap"/>They swap their mixtures, in public. <mark name="final"/>Then each adds its own secret to the other's mix.

<mark name="same"/>Both end up with exactly the same colour. <mark name="eve"/>Anyone listening saw only the mixtures, and paint can't be unmixed.

---

![](scenes/math.html)

Real TLS uses mathematics instead of paint. <mark name="curve"/>Mixing takes a moment, <mark name="hard"/>and unmixing is practically impossible, even for today's fastest computers.

<mark name="fresh"/>A fresh pair of secrets is made for every connection, then thrown away. <mark name="later"/>So even if the server's keys are stolen later, recordings of today's traffic stay locked.

<mark name="pq"/>And browsers now add a newer method to the mix, designed to hold up against future quantum computers.

---

![](scenes/mitm.html)

But a key exchange alone has a weak spot. <mark name="mitm"/>An attacker in the middle could swap paint with you, pretending to be the bank. <mark name="both"/>And swap with the bank, pretending to be you.

<mark name="relay"/>You'd have a private line, straight to the wrong person. <mark name="proof"/>So your browser needs proof of who's on the other end.

---

![](scenes/cert.html)

That proof is a certificate. <mark name="name"/>It names the site, <mark name="key"/>carries the site's public key, <mark name="issuer"/>and it's signed by a certificate authority, <mark name="checked"/>which first checked that whoever asked for it really controls that name.

---

![](scenes/sign.html)

The public key has a partner: a private key that never leaves the server. <mark name="sign"/>What the private key signs, <mark name="verify"/>anyone can check with the public key. <mark name="forge"/>But nobody else can fake it.

<mark name="proof"/>So in the handshake, the server signs the conversation so far. That proves the certificate is its own, and not a copy.

---

![](scenes/chain.html)

But why trust the authority? <mark name="chain"/>Its own certificate is signed by another, up a short chain, <mark name="root"/>to a root that's built into your browser or operating system.

Your browser checks <mark name="sigs"/>every signature, <mark name="name"/>the name, <mark name="dates"/>and the dates. <mark name="warn"/>If anything is off, you get a warning instead of a padlock.

---

![](scenes/handshake.html)

Put it all together, and you have the TLS handshake. <mark name="hello"/>Your browser says hello, with its half of the key exchange.

<mark name="reply"/>The server answers with its half, <mark name="cert"/>its certificate, <mark name="sig"/>and its signature. <mark name="fin"/>Your browser checks them, and both sides confirm they hold the same key.

<mark name="data"/>Then the real request goes, encrypted. <mark name="rtt"/>It all takes one trip there and back, usually quicker than a blink.

---

![](scenes/seal.html)

Every encrypted message also carries a <mark name="seal"/>seal, made with the shared key.

<mark name="flip"/>Change even one bit on the way, <mark name="broken"/>and the seal no longer matches. The browser throws the message out, and closes the connection.

---

![](scenes/limits.html)

HTTPS has limits. <mark name="hidden"/>It hides what you send and receive, even the rest of the address after the site's name.

<mark name="seen"/>But who you're talking to, the site's name and its internet address, can usually still be seen.

<mark name="padlock"/>And the padlock only says the connection is private, and the site controls its name. <mark name="scam"/>A scam site can have a padlock too.

---

![](scenes/close.html)

(overlay: none)

So next time you see the padlock, remember what it stands for. <mark name="key"/>A key, agreed in public. <mark name="seal"/>A seal on every message. <mark name="id"/>And an identity, checked up a chain of trust.

<mark name="end"/>All before the page has even loaded. That's HTTPS.

(pause: 3)
