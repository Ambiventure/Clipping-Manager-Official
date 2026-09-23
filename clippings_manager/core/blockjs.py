"""The scripts that run inside the page and say where the cutting is.

They run inside the page, in the browser, and answer one question between
them: which rectangle is the cutting? A news page is headline-first - the
headline, the picture under it and the first inches of the story. A social
post is a card of its own.

Deliberately not tag-driven: the Times of India puts its story in plain divs
with no <p> at all, so the body is found by weight of text, not by tag name.

THE ORDER THEY RUN IN (core/webshot.capture_over), and why each exists - every
one of these came from a capture that went wrong and was measured (NOTES:
"Capture quality: waiting, clearing, and the width"):

  PREPARE_PAGE     waits for the page's structure (never the load event:
                   Hindustan Times never finishes loading), asks lazy pictures
                   to load now, scrolls through the top of the page for the
                   ones that load only when seen, then waits - with limits -
                   for the pictures and the fonts. A cutting taken at a fixed
                   2.5 seconds came out with empty boxes where photos arrive
                   late.
  CLEAR_CLUTTER    hides adverts, walls, cookie bars and anything pinned to
                   the screen, lets a locked page scroll again and takes the
                   blur off. It hides by whole name tokens ("noAds" and
                   "ad-free" are not adverts) and never hides story text or
                   the lead picture: the sites' own names for their story
                   wrappers are full of "ad" and "taboola". Walls are told
                   apart first, so an ad-blocker notice with a headline of
                   its own still goes: anything fixed to the screen that
                   holds a heading and no story is a wall, whatever its
                   wording. A picture behind the headline is the lead only
                   within the page and the story's column (a wallpaper
                   advert is behind the headline too).
  FIND_BLOCK       measures the cutting. It is never narrower than the
                   headline, a rail beside the story is blanked rather than
                   cropped through, and an advert strip can end the cutting
                   only after the lead picture (India Today put one between
                   the standfirst and the photo, and the photo was lost).
                   Its padding never shows part of a line it did not keep.
  POSTER_FOR_PLAYER  a lead video with no picture of its own prints as the
                   page's own still, not as a black box.
  WAIT_BLOCK       the chosen rectangle's pictures, finished.
  SCROLL_TO        the page brought to the cutting: the picture is taken
                   inside the window, never beyond it (see webshot).
  CHECK_KEPT       where the kept things are now - nothing may have moved.
  RESTORE_PAGE     every change undone, for a page somebody is looking at.

EVERY CHANGE IS WRITTEN DOWN. A style or attribute changed on an element keeps
what it was in data-clip-prev; an element put in carries data-clip-added.
RESTORE_PAGE puts it all back, so a page a person is reading in the browser
window looks exactly as it did after its picture is taken.

Nothing here imports anything. These are strings; the browser runs them.
"""

#: How much of the story to show under the headline, in CSS pixels. Enough for
#: the picture and the opening paragraphs; a whole page prints too small.
BODY_RUN = 620
#: Nothing taller than this is ever captured, whatever the page looks like.
MOST_TALL = 2200

#: The address of a post's public card - what core/embedcard asks a site for
#: when a link points at a post. A twin of embedcard.is_card, in the page's own
#: language; test_embedcard holds the two to the same answers. A card is never
#: a wall, never carries an advert, and is cut to its own edges.
CARD_PAGE = (r"/^https:\/\/platform\.twitter\.com\/embed\/"
             r"|\/plugins\/post\.php"
             r"|instagram\.com\/(?:p|reel|tv)\/[^\/]+\/embed"
             r"|threads\.(?:net|com)\/@[^\/]+\/post\/[^\/]+\/embed"
             r"|linkedin\.com\/embed\/feed\/update\//i")

#: Shared by every script that changes the page: what an attribute was before
#: the first change, kept on the element itself so it can be put back.
_KEEP = r"""
  const PREV = 'data-clip-prev';
  const remember = (el, attr) => {
    let was = {};
    try { was = JSON.parse(el.getAttribute(PREV) || '{}') || {}; } catch (e) { was = {}; }
    if (!Object.prototype.hasOwnProperty.call(was, attr)) {
      was[attr] = el.getAttribute(attr);
      el.setAttribute(PREV, JSON.stringify(was));
    }
  };
  const setStyle = (el, prop, value) => { remember(el, 'style'); el.style.setProperty(prop, value, 'important'); };
  const setAttr = (el, attr, value) => { remember(el, attr); el.setAttribute(attr, value); };
  const dropAttr = (el, attr) => { if (el.hasAttribute(attr)) { remember(el, attr); el.removeAttribute(attr); } };
"""

# ------------------------------------------------------------------ prepare
#: Called as (PREPARE_PAGE)({...limits}). Returns JSON of what it did.
#: Called first of all on a post's card, before the site's own scripts have
#: built the post. See STILL_THE_VIDEO's comment for what it is for.
STILL_THE_VIDEO = r"""
(() => {
  // A POST'S VIDEO IS NEVER PLAYED, AND THE CARD IS NEVER TOLD SO.
  //
  // A cutting is a still picture: nothing is ever gained by playing the video,
  // and on X everything is lost by trying. The browser inside the program has
  // no H.264 of its own - Qt's engine is built without it - so an X card's
  // player fails a second or two after it starts, and X answers that by
  // throwing the whole card away and drawing "The media could not be played"
  // in its place. Not the picture: the WHOLE card, 560 x 897 of grey, headline
  // and all. Measured in the browser inside the app: three runs of two posts,
  // six of six lost. In the program's own Chrome, which does have the codecs,
  // fifteen of fifteen came out right - so this was invisible until it was
  // captured the way the office captures.
  //
  // The cure is to make sure the player never gets as far as failing. Where it
  // has no source it stays exactly as it starts: the poster frame, the play
  // button over it, and readyState 0 - which is what the captures that DID
  // come out right were showing. So load() does nothing, play() returns a
  // promise that never settles (never resolving is what a paused player looks
  // like; REJECTING is an error, and the error is the thing being avoided),
  // and a source set on the element goes nowhere.
  //
  // Only on a card, and only in the page. Nothing here reaches a page somebody
  // is reading in the browser window: capture_current never calls it.
  const proto = window.HTMLMediaElement && HTMLMediaElement.prototype;
  if (!proto || proto.__clipStilled) return 'no media element';
  proto.__clipStilled = true;
  proto.load = function () {};
  proto.play = function () { return new Promise(function () {}); };
  const drop = (name) => {
    try {
      const was = Object.getOwnPropertyDescriptor(proto, name);
      if (!was || !was.set) return;
      Object.defineProperty(proto, name, {
        configurable: true, enumerable: was.enumerable,
        get: was.get ? function () { return was.get.call(this); } : undefined,
        set: function () {},
      });
    } catch (e) { /* a browser that will not have it keeps its own */ }
  };
  drop('src');
  drop('srcObject');
  // AND THE CARD IS NEVER TOLD THAT IT CANNOT PLAY. This is what actually
  // does it. Measured in the browser inside the app: canPlayType for
  // 'video/mp4; codecs="avc1.42E01E"' answers "" and
  // MediaSource.isTypeSupported answers false, because Qt's engine is built
  // without H.264. X ASKS, is told no, and throws the whole card away for a
  // grey "The media could not be played" - headline and all. Told yes, it
  // draws the player it always draws: the poster frame with the play button
  // over it, which is exactly the cutting wanted. Nothing is ever decoded,
  // because load() above does nothing and no source is ever set.
  const asked = proto.canPlayType;
  proto.canPlayType = function (type) {
    return /mp4|avc1|h264|mpeg|m4a|aac/i.test(String(type || ''))
      ? 'probably' : asked.call(this, type);
  };
  if (window.MediaSource && MediaSource.isTypeSupported) {
    const wasSupported = MediaSource.isTypeSupported;
    MediaSource.isTypeSupported = function (type) {
      return /mp4|avc1|h264|mpeg|m4a|aac/i.test(String(type || ''))
        ? true : wasSupported.call(this, type);
    };
  }
  // One that is already on the page, put back to where it starts.
  for (const v of document.querySelectorAll('video, audio')) {
    try { v.pause(); } catch (e) { /* not started */ }
    v.removeAttribute('autoplay');
    v.setAttribute('preload', 'none');
  }
  return 'stilled';
})()
"""

PREPARE_PAGE = r"""
(async (opts) => {
  opts = Object.assign({domMs: 4000, scrollLimit: 3000, stepPause: 120, imageMs: 4000, fontsMs: 1500,
                        scroll: true, promote: true}, opts || {});
  /*KEEP*/
  const t0 = performance.now();
  const ms = () => Math.round(performance.now() - t0);
  const sleep = n => new Promise(r => setTimeout(r, n));
  // A frame, or 120 ms if frames are not being drawn: a page nobody can see
  // may never draw one, and a wait on it would be a wait for ever.
  const frame = () => Promise.race([new Promise(r => requestAnimationFrame(() => r())), sleep(120)]);
  const within = (p, n) => Promise.race([Promise.resolve(p).then(() => true, () => true), sleep(n).then(() => false)]);
  const go = y => { try { scrollTo({left: 0, top: y, behavior: 'instant'}); } catch (e) { scrollTo(0, y); } };
  const out = {readyAtStart: document.readyState};
  // The page's structure, never its load event: ad-heavy pages sit at
  // "interactive" for seconds, and some never finish loading at all.
  if (document.readyState === 'loading')
    out.dom = await within(new Promise(r => document.addEventListener('DOMContentLoaded', r, {once: true})), opts.domMs);

  let eager = 0, promoted = 0;
  if (opts.promote) {
    const PLACEHOLDER = /^data:|^about:|1x1|blank\.|spacer|placeholder|transparent|lazy|loading|default[-_]?(img|image)|grey\.|gray\./i;
    const promote = (el, from, to) => {
      const v = el.getAttribute(from);
      if (!v || /^data:/.test(v)) return;
      const cur = el.getAttribute(to) || '';
      if (cur === v) return;
      if (!cur || PLACEHOLDER.test(cur)) { setAttr(el, to, v); promoted++; }
    };
    for (const el of document.querySelectorAll('img')) {
      if ((el.getAttribute('loading') || '').toLowerCase() === 'lazy') { setAttr(el, 'loading', 'eager'); eager++; }
      for (const a of ['data-src', 'data-lazy-src', 'data-original', 'data-lazy', 'data-hi-res-src']) promote(el, a, 'src');
      for (const a of ['data-srcset', 'data-lazy-srcset']) promote(el, a, 'srcset');
    }
    for (const el of document.querySelectorAll('picture source')) { promote(el, 'data-srcset', 'srcset'); promote(el, 'data-src', 'srcset'); }
    for (const el of document.querySelectorAll('video[data-poster]')) promote(el, 'data-poster', 'poster');
    for (const el of document.querySelectorAll('[data-bg], [data-background-image], [data-bg-src]')) {
      const v = el.getAttribute('data-bg') || el.getAttribute('data-background-image') || el.getAttribute('data-bg-src');
      if (v && getComputedStyle(el).backgroundImage === 'none') {
        remember(el, 'style');
        el.style.setProperty('background-image', /^url\(/.test(v) ? v : 'url("' + v + '")');
        promoted++;
      }
    }
  }
  out.eager = eager; out.promoted = promoted;

  const heads = [...document.querySelectorAll('h1')].filter(h => (h.innerText || '').trim().length > 15);
  const headTop = heads.length ? Math.min(...heads.map(h => h.getBoundingClientRect().top + scrollY)) : 0;
  let steps = 0;
  if (opts.scroll) {
    // Only the top of the page: far enough for pictures that load when they
    // are seen, not so far that a "next story" feed takes the page over.
    const limit = Math.min(document.documentElement.scrollHeight, headTop + opts.scrollLimit);
    const step = Math.max(400, Math.round(innerHeight * 0.7));
    for (let y = step; y - step < limit - innerHeight; y += step) { go(y); steps++; await frame(); await sleep(opts.stepPause); }
    go(0); await frame(); await sleep(opts.stepPause);
  }
  out.steps = steps;

  const region = headTop + 2600;
  const pending = [];
  const waitImg = img => img.decode ? img.decode().catch(() => {})
      : new Promise(r => { img.addEventListener('load', r, {once: true}); img.addEventListener('error', r, {once: true}); });
  for (const img of document.querySelectorAll('img')) {
    const r = img.getBoundingClientRect();
    if (r.width * r.height < 2500 || r.top + scrollY > region) continue;
    if (img.complete && img.naturalWidth > 0) continue;
    if (!img.currentSrc && !img.getAttribute('src') && !img.getAttribute('srcset')) continue;
    pending.push(waitImg(img));
  }
  // Pictures drawn as a background (X draws a post's photo that way) and a
  // video's still are not <img>s: they are asked for, and waited on, too.
  const urls = new Set();
  for (const el of document.querySelectorAll('div, span, a, figure, section, header, i, button')) {
    const r = el.getBoundingClientRect();
    if (r.width * r.height < 20000 || r.top + scrollY > region || r.bottom + scrollY < 0) continue;
    const m = (getComputedStyle(el).backgroundImage || '').match(/url\(["']?([^"')]+)["']?\)/);
    if (m && !/^data:/.test(m[1])) urls.add(m[1]);
  }
  for (const v of document.querySelectorAll('video[poster]')) if (v.poster && !/^data:/.test(v.poster)) urls.add(v.poster);
  for (const u of urls) { const im = new Image(); im.src = u; if (!(im.complete && im.naturalWidth)) pending.push(waitImg(im)); }
  out.pending = pending.length;
  out.imagesDone = await within(Promise.all(pending), opts.imageMs);
  // A headline measured before its font arrives wraps differently after.
  if (document.fonts && document.fonts.status !== 'loaded') out.fontsDone = await within(document.fonts.ready, opts.fontsMs);
  out.fonts = document.fonts ? document.fonts.status : 'n/a';
  await frame(); await frame();
  out.readyState = document.readyState;
  out.ms = ms();
  return JSON.stringify(out);
})
"""

# ------------------------------------------------------------------- clutter
#: Called as (CLEAR_CLUTTER)({asIs: false}). Synchronous, and safe to run twice:
#: a second run over the same page hides nothing new.
CLEAR_CLUTTER = r"""
((opts) => {
  opts = opts || {};
  /*KEEP*/
  /*CARD*/
  // A CARD IS ALREADY ONLY THE POST. It is what a site hands a newspaper to
  // put in its own page: one post, no feed, no rail, no advert, nothing
  // pinned over it. Everything below is written for a news page and would
  // read a card wrongly - X's card is one <article> laid over the page, which
  // the pinned-over-the-page rule hides, and the "open in the app" strip at
  // the foot of Instagram's card is part of the card the office is quoting,
  // not a banner over somebody's reading. So on a card this stops here, and
  // the only thing looked for is the cookie notice a site may still draw over
  // it (never the card itself, which is why it is asked for by name).
  if (card) {
    const notices = [];
    // A player with nothing under it: put its own poster frame in its place,
    // so a card whose picture is the video still comes out as a picture. X
    // draws a poster image of its own under the player and this finds it
    // already there; this is for the card that does not.
    for (const v of document.querySelectorAll('video[poster]')) {
      const r = v.getBoundingClientRect();
      if (r.width < 60 || r.height < 60) continue;
      const near = [...(v.parentElement ? v.parentElement.querySelectorAll('img') : [])]
        .filter(i => i.complete && i.naturalWidth > 80);
      if (near.length || v.hasAttribute('data-clip-stood-in')) continue;
      const img = document.createElement('img');
      img.src = v.poster;
      img.setAttribute('data-clip-added', '1');
      img.setAttribute('data-clip-poster', '1');
      img.style.cssText = 'display:block;width:' + r.width + 'px;height:'
        + r.height + 'px;object-fit:cover;margin:0;';
      v.setAttribute('data-clip-stood-in', '1');
      v.parentElement.insertBefore(img, v);
      setStyle(v, 'display', 'none');
      notices.push('the poster in place of the player');
    }
    const drop = (el, why) => {
      const r = el.getBoundingClientRect();
      // Never anything big: the post itself is the big thing on a card, and
      // a rule that could hide it is not worth having.
      if (r.width < 3 || r.height < 3 || r.height > 120) return;
      setStyle(el, 'display', 'none');
      el.setAttribute('data-clip-hidden', why);
      notices.push(why + ' ' + el.tagName.toLowerCase());
    };
    for (const el of document.querySelectorAll(
        '[data-cookiebanner], [id*="cookie" i][role="dialog"], [class*="cookie-banner" i]')) {
      if (el.getBoundingClientRect().height < innerHeight * 0.5) drop(el, 'cookie notice');
    }
    // A card's own controls. Instagram ends its card with a box to write a
    // comment in and its logo again, and puts a "View more on Instagram"
    // button under the picture: both are for somebody reading it on the site,
    // and neither is part of the post being quoted. Asked for by the names
    // Instagram gives them, so nothing else can be caught by them, and the
    // card's "this post is not available" box (EmbedIsBroken) is left alone -
    // its words are how the program knows there is no post.
    for (const el of document.querySelectorAll('.Footer, .PrimaryCTA')) {
      drop(el, "the card's own button");
    }
    return JSON.stringify({ card: true, names: notices, fresh: notices.length });
  }
  const words = el => (el.innerText || '').trim();
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const short = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
      + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const HIDDEN = 'data-clip-hidden';
  const SKIP = new Set(['HTML', 'BODY', 'MAIN', 'H1']);
  const stats = {adNames: [], adLabels: [], adFrames: [], collapsed: 0, guarded: [], fixed: 0, sticky: 0,
                 keptFixed: [], modals: [], unlocked: [], unblurred: 0, paused: 0, fresh: 0, names: [], lead: ''};
  const hide = (el, why) => {
    if (el.hasAttribute(HIDDEN)) return;
    setStyle(el, 'display', 'none');
    el.setAttribute(HIDDEN, why);
    stats.fresh++;
    if (stats.names.length < 60) stats.names.push(why + ' ' + short(el));
  };
  // Story text is never an advert: long, and mostly not links. Hindustan
  // Times keeps its whole story in an element named "taboola-readmore".
  const storyText = el => {
    const all = words(el).length;
    if (all < 300) return false;
    let linked = 0;
    for (const a of el.querySelectorAll('a')) linked += words(a).length;
    return linked / all < 0.5;
  };
  // Whole words of an element's class and id, camelCase split too. Never a
  // substring: TOI's lead picture is "vdo_embedd" and Bhaskar's news list is
  // named with hashes like "ad3ccf1a".
  const tokens = el => {
    const cls = typeof el.className === 'string' ? el.className : ((el.className && el.className.baseVal) || '');
    return (cls + ' ' + (el.id || '')).replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  };
  const viewArea = innerWidth * innerHeight;

  // Advert names. A "network" name is an advert network's own (div-gpt-ad,
  // adslot, taboola); a "plain" one is an ordinary word for an advert.
  const NETWORK = new Set(['adsbygoogle', 'taboola', 'outbrain', 'colombia', 'izooto', 'teads', 'mgid', 'adsense', 'skinning',
      'adslot', 'adunit', 'adbox', 'adcontainer', 'adwrapper', 'dfp', 'googleads', 'vdoai', 'gptad', 'admanager']);
  const PLAIN = new Set(['ad', 'ads', 'advert', 'adverts', 'advertisement', 'advertisements', 'sponsor', 'sponsored', 'promoted', 'mrec', 'leaderboard']);
  const SIZED = /^ads?\d{2,3}(x\d{2,3})?$/;
  // A word that says there is no advert: "noAds", "non-ad", "ad-free",
  // "without-ads". Counted as an advert, the lead photo inside was hidden.
  const ADWORD = new Set(['ad', 'ads', 'advert', 'adverts', 'advertisement', 'advertisements']);
  const NO_BEFORE = new Set(['no', 'non', 'without', 'zero']);
  const NO_AFTER = new Set(['free', 'less', 'none']);
  const negated = (t, i) => ADWORD.has(t[i]) && (NO_BEFORE.has(t[i - 1]) || NO_AFTER.has(t[i + 1]));
  const adKind = el => {
    const t = tokens(el);
    const pairs = t.slice(1).map((w, i) => t[i] + w);
    if (t.some(w => NETWORK.has(w)) || pairs.some(w => NETWORK.has(w))) return 'network';
    if (t.some((w, i) => (PLAIN.has(w) || SIZED.test(w)) && !negated(t, i))) return 'plain';
    return '';
  };

  // Walls are told apart first, before anything is kept for holding the
  // headline: an ad-blocker notice can have an <h1> of its own ("Ad Blocker
  // Detected"), and a wall counted as the headline's holder was kept while
  // the story was cut away from around it. The wording is only a help - a
  // wall is known by what it is, too (see `bare` below) - but it is the
  // wording the sites use: "It looks like you're using an ad blocker", the
  // Hindi sites' "ऐड ब्लॉकर", "Register free to continue reading".
  const WALL_TEXT = new RegExp('(ad.?block(er)?\\s+(detected|enabled|is on)'
    + "|((it\\s+)?(looks|seems)\\s+like\\s+)?you('re|’re|\\s+are)\\s+using\\s+an?\\s+ad.?block(er)?"
    + '|(using|running)\\s+an?\\s+ad.?block|detected\\s+(an?\\s+)?ad.?block'
    + '|turn off (your )?ad.?block|disable (your )?ad.?block|whitelist (us|our)|allow ads'
    + '|(register|sign up|subscribe|log ?in|sign in)\\s+((for\\s+)?free\\s+|now\\s+)?to\\s+(continue|keep)\\s+reading'
    + '|(ऐ|ए)ड\\s?ब्लॉकर)', 'i');
  const WALL = new Set(['modal', 'popup', 'overlay', 'backdrop', 'interstitial', 'lightbox', 'adblock', 'adblocker', 'blocker',
      'paywall', 'consent', 'cookie', 'cookies', 'gdpr', 'onesignal', 'notification', 'subscribe']);
  const DIALOG = 'dialog[open], [role=dialog], [role=alertdialog], [aria-modal=true]';
  const pinned = [];
  for (const el of document.querySelectorAll('body *')) {
    if (SKIP.has(el.tagName) || el.hasAttribute(HIDDEN)) continue;
    const s = getComputedStyle(el);
    if (s.display === 'none') continue;
    const dialog = el.matches(DIALOG);
    if (dialog || s.position === 'fixed' || s.position === 'sticky'
        || (s.position === 'absolute' && (parseInt(s.zIndex, 10) || 0) >= 100)) pinned.push({el, s, dialog});
  }
  const allHeads = [...document.querySelectorAll('h1')].filter(h => vis(h) && words(h).length > 15);
  // What a pinned thing says, without the words of the headlines it holds:
  // a story headed "Railway Board to allow ads on Vande Bharat coaches", laid
  // over its photo, said "allow ads" in its own headline and was hidden as an
  // ad-blocker wall. A headline that is mostly a wall's words ("Ad Blocker
  // Detected") is the wall's own, and still counts.
  const mostlyWall = h => { const own = words(h), hit = own.match(WALL_TEXT); return !!hit && hit[0].length >= own.length * 0.5; };
  const wallSays = el => {
    let text = words(el);
    for (const h of allHeads) {
      if (!el.contains(h) || mostlyWall(h)) continue;
      text = text.split(words(h)).join(' ');
    }
    return WALL_TEXT.test(text.slice(0, 400));
  };
  // Pinned to the screen - fixed or sticky - with no story of its own. 2.0.31
  // hid everything pinned before it measured. Kept instead for holding a
  // headline, a sign-up wall's "Register free to continue reading this
  // story", set back in the page, was bigger than the story's headline and
  // became the whole cutting; so was an ad-blocker notice worded any way but
  // the few phrases above, in English or in Hindi.
  const bare = pinned.filter(c => (c.s.position === 'fixed' || c.s.position === 'sticky') && !storyText(c.el));
  const wallish = c => {
    // Headed only by a wall's own words ("Ad Blocker Detected"): a wall,
    // however long the instructions under the heading run.
    const held = allHeads.filter(h => c.el.contains(h));
    if (held.length && held.every(mostlyWall)) return true;
    const r = c.el.getBoundingClientRect();
    const said = wallSays(c.el);
    // A wall's name counts only for what is pinned to the screen or is a
    // dialog. A layer inside the story laid over its photo is named
    // "hero-overlay" and holds the headline: counted, the headline went.
    const named = (c.dialog || c.s.position === 'fixed')
      && tokens(c.el).some(x => WALL.has(x)) && r.width * r.height > viewArea * 0.2;
    // A story opened in a dialog of its own is not a wall: it has story text
    // and says nothing of ad-blockers.
    if (c.dialog) return said || named || !storyText(c.el);
    // A page wrapper pinned in place to stop the page scrolling holds the
    // story itself: that is let flow again below, never taken for a wall.
    // Nor is a layer laid over the photo that says nothing of walls.
    if (!bare.includes(c)) return (said || named) && !storyText(c.el);
    // Fixed, holding a heading and no story: a wall, whatever it says.
    if (said || named || c.s.position === 'fixed') return true;
    // Sticky stays where the page lays it, and a story's own heading block
    // can be sticky: that is a wall only when the page has a headline
    // somewhere else to take instead.
    return allHeads.some(h => !h.closest(DIALOG) && !bare.some(b => b.el.contains(h)));
  };
  const walls = pinned.filter(c => allHeads.some(h => c.el.contains(h)) && wallish(c)).map(c => c.el);
  const heads = allHeads.filter(h => !walls.some(w => w.contains(h)));
  const holdsHead = el => heads.some(h => el.contains(h));
  const guarded = el => SKIP.has(el.tagName) || holdsHead(el) || storyText(el);

  // The lead picture - the first photo-shaped picture under the headline, in
  // its column, as FIND_BLOCK will choose it - is never hidden for a name or
  // a label. "leadMedia noAds" and "story-image ad-free" are names too, and
  // the photo went with them.
  let lead = null;
  const head0 = heads.map(h => ({ h, r: h.getBoundingClientRect(), boxed: h.closest(DIALOG) ? 1 : 0 }))
    .sort((a, b) => (a.boxed - b.boxed) || (b.r.width * b.r.height - a.r.width * a.r.height))[0];
  // A picture the headline is laid over counts only when it lies within the
  // page and is not much wider than the story's column (FIND_BLOCK reads it
  // the same way). A wallpaper advert 1920 wide behind a 760 story has the
  // headline over it too: taken as the lead photo, it was shielded from
  // being hidden and widened the cutting to 1952, mostly advert.
  const pageLeft = Math.min(0, document.documentElement.clientWidth - innerWidth) - 2;
  const pageRight = Math.max(document.documentElement.clientWidth, innerWidth) + 2;
  // The column: the nearest box round the headline that holds the story's
  // first words as well.
  const columnOf = h => {
    const own = words(h).length;
    for (let e = h.parentElement; e && e !== document.documentElement; e = e.parentElement)
      if (words(e).length - own >= 200) return Math.max(e.getBoundingClientRect().width, h.getBoundingClientRect().width);
    return document.documentElement.clientWidth;
  };
  // Inside an advert network's own wrapper (div-gpt-ad, adslot), with no
  // story and no headline in it. "story-ad-wrap" is a plain name and still
  // guarded; Hindustan Times' "taboola-readmore" holds the story and is too.
  const inAdvert = el => {
    for (let e = el; e && e !== document.body; e = e.parentElement)
      if (adKind(e) === 'network' && !storyText(e) && !holdsHead(e)) return true;
    return false;
  };
  if (head0) {
    const hr = head0.r, colW = columnOf(head0.h);
    for (const el of document.querySelectorAll('figure, img, picture, video')) {
      const r = el.getBoundingClientRect();
      const mid = (r.left + r.right) / 2;
      // A photo with the headline laid over it counts as well as one under it.
      const under = r.top < hr.top && r.bottom >= hr.bottom - 4 && r.left <= hr.left + 4 && r.right >= hr.right - 4
        && r.left >= pageLeft && r.right <= pageRight && r.width <= colW * 1.5;
      if (!(r.width > 2 && r.height > 2) || (r.top < hr.top - 4 && !under) || r.top >= hr.bottom + 1200) continue;
      if (mid <= hr.left - 60 || mid >= hr.right + 60 || r.width <= hr.width * 0.3 || r.width * r.height <= 25000) continue;
      // An advert's shape is not a photo's: 728 x 90, 970 x 250, 300 x 250.
      if (r.width < hr.width * 0.5 || r.height < r.width * 0.3) continue;
      if (inAdvert(el)) continue;
      lead = el.matches('figure') ? (el.querySelector('img, picture, video') || el) : el;
      break;
    }
  }
  if (lead) stats.lead = short(lead);
  const holdsLead = el => !!lead && el.contains(lead);
  const kept = el => guarded(el) || holdsLead(el);

  // A wrapper an advert leaves empty would print as a blank gap.
  const collapseUp = el => {
    for (let p = el.parentElement, i = 0; p && i < 3; p = p.parentElement, i++) {
      if (kept(p) || p.hasAttribute(HIDDEN)) return;
      const live = [...p.children].filter(c => !c.hasAttribute(HIDDEN) && vis(c)
          && (words(c).length > 20 || c.querySelector('img, picture, video, svg')));
      if (live.length || words(p).length > 20) return;
      hide(p, 'emptied'); stats.collapsed++;
    }
  };

  for (const el of document.querySelectorAll('body *')) {
    if (el.hasAttribute(HIDDEN) || el.closest('[' + HIDDEN + ']')) continue;
    const kind = adKind(el);
    if (!kind) continue;
    if (kept(el)) { if (stats.guarded.length < 6) stats.guarded.push(short(el)); continue; }
    if (kind === 'plain' && words(el).length > 160) continue;
    hide(el, 'ad-name'); stats.adNames.push(short(el)); collapseUp(el);
  }

  // A box labelled "Advertisement" and not much more. "Advertise" is not a
  // label: it is the footer link on NDTV.
  const LABEL = /^(advertisement|advertisment|sponsored|sponsored content|promoted|ad|ads|विज्ञापन|ਇਸ਼ਤਿਹਾਰ)$/i;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const labels = [];
  while (walker.nextNode()) if (LABEL.test(walker.currentNode.nodeValue.trim())) labels.push(walker.currentNode.parentElement);
  for (const p of labels) {
    if (!p || p.closest('[' + HIDDEN + ']') || kept(p) || p.closest('a, nav, footer, li')) continue;
    const said = words(p).length;
    let box = p;
    for (let up = p.parentElement, i = 0; up && up !== document.body && i < 5; up = up.parentElement, i++) {
      if (kept(up) || words(up).length > said + 40) break;
      if ([...up.querySelectorAll('p')].some(q => words(q).length > 80)) break;
      box = up;
    }
    hide(box, 'ad-label'); stats.adLabels.push(short(box)); collapseUp(box);
  }

  const AD_HOST = /(^|\.)(doubleclick\.net|googlesyndication\.com|amazon-adsystem\.com|adnxs\.com|taboola\.com|outbrain\.com|criteo\.com|pubmatic\.com|teads\.tv|vdo\.ai|mgid\.com|izooto\.com|adservice\.google\.[a-z.]+)$/i;
  for (const f of document.querySelectorAll('iframe, ins')) {
    if (f.closest('[' + HIDDEN + ']')) continue;
    let host = '';
    try { host = new URL(f.getAttribute('src') || '', location.href).hostname; } catch (e) {}
    const named = /^(google_ads_iframe|aswift_|google_ads_top_frame|goog_plcm_frame)/.test(f.id || '') || f.classList.contains('adsbygoogle');
    if (!(AD_HOST.test(host) || named || f.tagName === 'INS')) continue;
    let box = f;
    for (let up = f.parentElement, i = 0; up && up !== document.body && i < 3; up = up.parentElement, i++) {
      if (kept(up) || words(up).length > 40) break;
      box = up;
    }
    hide(box, 'ad-frame'); stats.adFrames.push(short(box)); collapseUp(box);
  }

  // Walls: an ad-blocker notice, a modal and its backdrop, a cookie or
  // notification prompt, anything pinned over the page. A wall told apart
  // above goes whatever it holds. A page wrapper pinned in place to stop the
  // page scrolling holds the headline: it is let flow again, never hidden, or
  // the story goes with it.
  for (const c of pinned) {
    const el = c.el, s = c.s, dialog = c.dialog;
    if (el.hasAttribute(HIDDEN) || el.closest('[' + HIDDEN + ']')) continue;
    if (s.display === 'none') continue;
    if (walls.includes(el)) { hide(el, 'wall'); stats.modals.push(short(el)); continue; }
    const floating = s.position === 'fixed' || s.position === 'sticky';
    const abs = s.position === 'absolute' && (parseInt(s.zIndex, 10) || 0) >= 100;
    if (!floating && !dialog && !abs) continue;
    if (holdsHead(el)) {
      if (floating) { setStyle(el, 'position', 'static'); stats.keptFixed.push(short(el)); }
      continue;
    }
    if (floating) { const was = s.position; hide(el, was); was === 'fixed' ? stats.fixed++ : stats.sticky++; continue; }
    const r = el.getBoundingClientRect();
    const named = tokens(el).some(x => WALL.has(x));
    if (dialog || (named && r.width * r.height > viewArea * 0.2) || WALL_TEXT.test(words(el).slice(0, 400))) {
      hide(el, 'wall'); stats.modals.push(short(el));
    }
  }

  for (const el of [document.documentElement, document.body]) {
    if (!el) continue;
    const s = getComputedStyle(el);
    if (/hidden|clip/.test(s.overflowY)) { setStyle(el, 'overflow-y', 'visible'); stats.unlocked.push(el.tagName + ':overflow'); }
    if (s.position === 'fixed') { setStyle(el, 'position', 'static'); stats.unlocked.push(el.tagName + ':fixed'); }
    for (const c of ['modal-open', 'no-scroll', 'noscroll', 'overflow-hidden', 'scroll-lock', 'tp-modal-open', 'disable-scroll'])
      if (el.classList.contains(c)) { remember(el, 'class'); el.classList.remove(c); stats.unlocked.push(el.tagName + ':' + c); }
  }
  const touched = new Set();
  for (const h of heads) for (let up = h; up && up !== document.documentElement; up = up.parentElement) touched.add(up);
  for (const el of document.querySelectorAll('body > *, body > * > *')) touched.add(el);
  for (const el of touched) {
    const s = getComputedStyle(el);
    if ((s.filter && s.filter.includes('blur')) || (s.backdropFilter && s.backdropFilter.includes('blur'))) {
      setStyle(el, 'filter', 'none'); setStyle(el, 'backdrop-filter', 'none'); stats.unblurred++; }
    if (parseFloat(s.opacity) < 0.9 && heads.some(h => el.contains(h))) { setStyle(el, 'opacity', '1'); stats.unblurred++; }
  }

  // A playing video is stopped and shown by its still - but never on a page
  // somebody is watching: that is theirs to play.
  if (!opts.asIs) {
    for (const v of document.querySelectorAll('video')) {
      if (v.closest('[' + HIDDEN + ']')) continue;
      try {
        if (!v.paused) { v.pause(); stats.paused++; }
        dropAttr(v, 'autoplay');
        if (v.poster && v.currentTime > 0) { setAttr(v, 'preload', 'none'); v.load(); }
      } catch (e) {}
    }
  }
  stats.hidden = document.querySelectorAll('[' + HIDDEN + ']').length;
  for (const k of ['adNames', 'adLabels', 'adFrames']) stats[k] = stats[k].slice(0, 10);
  return JSON.stringify(stats);
})
"""

# -------------------------------------------------------------------- block
FIND_BLOCK = r"""
(() => {
  /*KEEP*/
  /*CARD*/
  const seen = r => r.width > 2 && r.height > 2;
  const area = r => r.width * r.height;
  const words = el => (el.innerText || '').trim();
  const short = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
      + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const union = rs => ({ left: Math.min(...rs.map(r => r.left)), right: Math.max(...rs.map(r => r.right)),
                         top: Math.min(...rs.map(r => r.top)), bottom: Math.max(...rs.map(r => r.bottom)) });
  // Whole words of an element's class and id, camelCase split too, as
  // CLEAR_CLUTTER reads them. Never a substring: "ad" is inside "lead",
  // "subhead", "shadow", "download" and "Moradabad", and a first paragraph
  // styled class="lead" ended the cutting at the photo's caption.
  const tokens = el => {
    const cls = typeof el.className === 'string' ? el.className : ((el.className && el.className.baseVal) || '');
    return (cls + ' ' + (el.id || '')).replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  };
  const ADWORD = new Set(['ad', 'ads', 'advert', 'adverts', 'advertisement', 'advertisements']);
  const SIZED = /^ads?\d{1,3}(x\d{2,3})?$/;
  // "noAds", "non-ad", "ad-free": a word that says there is no advert.
  const negated = (t, i) => ADWORD.has(t[i])
    && (['no', 'non', 'without', 'zero'].includes(t[i - 1]) || ['free', 'less', 'none'].includes(t[i + 1]));
  // Named as one of these words (or, for `starts`, a word beginning with one)
  // - or two words run together, "also-read" as "alsoread".
  const namedAs = (el, exact, starts) => {
    const t = tokens(el);
    return t.some((w, i) => (exact.has(w) || SIZED.test(w) || (starts || []).some(s => w.startsWith(s))) && !negated(t, i))
      || t.slice(1).some((w, i) => exact.has(t[i] + w));
  };
  // A colour as rgb(), whatever syntax the page wrote it in. Chrome hands a
  // colour back the way it was written - oklch(0.97 0 0), color(srgb ...) -
  // and the margin painted from "0.97 0 0" came out black. A canvas turns any
  // colour it can draw into numbers. Mostly see-through counts as none.
  let paint = null;
  const solid = c => {
    if (!c || c === 'transparent') return null;
    try {
      if (!paint) { const cv = document.createElement('canvas'); cv.width = cv.height = 1; paint = cv.getContext('2d', { willReadFrequently: true }); }
      paint.clearRect(0, 0, 1, 1);
      paint.fillStyle = '#010203';
      paint.fillStyle = c;
      if (paint.fillStyle === '#010203' && !/^#010203$/i.test(c)) return null;
      paint.fillRect(0, 0, 1, 1);
      const d = paint.getImageData(0, 0, 1, 1).data;
      return d[3] < 128 ? null : 'rgb(' + d[0] + ', ' + d[1] + ', ' + d[2] + ')';
    } catch (e) { return null; }
  };
  const bgOf = el => solid(getComputedStyle(el).backgroundColor);
  // The colour behind an element: its own background, or the nearest
  // ancestor's that has one.
  const behind = (el, fallback) => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const c = bgOf(e); if (c) return c; }
    return fallback;
  };
  // Where the WORDS of an element reach, not its box: a headline's box can be
  // the width of the page while its words wrap early, or centred inside it.
  const wordsRect = el => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const rs = [...range.getClientRects()].filter(seen);
    return rs.length ? union(rs) : el.getBoundingClientRect();
  };
  const kept = [];

  // A wall instead of a page: X and Facebook show one to anybody not signed
  // in. A post that is on the page anyway - signed-out X shows it inside a
  // bare <article> - is a post, not a wall.
  const wall = document.querySelector(
    '[data-testid="loginButton"], [data-testid="LoginForm_Login_Button"], '
    + '#login_form, [action*="/login"][method="post"]');
  const social = /(^|\.)(x\.com|twitter\.com|facebook\.com|instagram\.com|threads\.net)$/i.test(location.hostname);
  // A bare <article> is a post only where it can be one: on a social site,
  // behind a sign-in wall, or as the page's own column (signed-out X, as
  // served, is a bare article 600 of 820 wide). Elsewhere a strip of teaser
  // cards above a story is a row of <article>s, and the page came out as the
  // first teaser.
  const mainColumn = el => !el.closest('nav, header, footer, aside')
    && el.getBoundingClientRect().width >= document.documentElement.clientWidth * 0.5;
  const postEls = [...document.querySelectorAll('[data-testid="tweet"], article[role="article"], div[role="article"], article')]
    .filter(el => seen(el.getBoundingClientRect()) && (el.querySelector('img, video') || words(el).length > 40))
    .filter(el => el.matches('[data-testid="tweet"], [role="article"]') || social || wall || mainColumn(el));
  const own = postEls[0] || null;

  // The largest headline, but one inside a dialog only when there is no
  // other: an ad-blocker notice's own <h1> is never the story's. Nor, while
  // there is another, is one pinned to the screen in a box with no story
  // round it - CLEAR_CLUTTER takes that box for a wall and hides it, and this
  // chooses the same way when the page has not been cleared.
  const DIALOG = 'dialog[open], [role=dialog], [role=alertdialog], [aria-modal=true]';
  const storyText = el => {
    const all = words(el).length;
    if (all < 300) return false;
    let linked = 0;
    for (const a of el.querySelectorAll('a')) linked += words(a).length;
    return linked / all < 0.5;
  };
  const pinnedBare = el => {
    for (let e = el; e && e.nodeType === 1 && e !== document.body; e = e.parentElement) {
      const p = getComputedStyle(e).position;
      if ((p === 'fixed' || p === 'sticky') && !storyText(e)) return true;
    }
    return false;
  };
  const heads = [...document.querySelectorAll('h1')]
    .map(el => ({ el, r: el.getBoundingClientRect(), boxed: el.closest(DIALOG) ? 1 : 0 }))
    .filter(h => seen(h.r) && words(h.el).length > 15)
    .map(h => Object.assign(h, { bare: pinnedBare(h.el) ? 1 : 0 }))
    .sort((a, b) => (a.boxed - b.boxed) || (a.bare - b.bare) || (area(b.r) - area(a.r)));
  const head = heads[0];

  if (!card && (wall || social) && !own && !(head && !social)) {
    return JSON.stringify({
      blocked: social
        ? 'that post could not be read. Either it needs you to be signed in - sign in to it in '
          + 'the browser inside the app, or take it from your Chrome - or the post has been taken down.'
        : 'that page wants you to be signed in. Sign in to it in the browser inside the app, or '
          + 'take it from your Chrome, and try again.',
      blockedKind: 'sign-in',
      site: location.hostname.replace(/^www\./, ''),
      href: location.href,
    });
  }

  let box = null, title = '', kind = '';
  let keptLines = [];
  const rails = [];
  const notes = [];

  if (card) {
    // THE CARD, CUT TO ITS OWN EDGES. Its page holds nothing else, so the
    // cutting is everything painted on it: every picture, and every element
    // with writing of its own. Taking the body instead left the card sitting
    // in whatever width the window happened to be - X draws 550 of the 820 -
    // with the rest white down one side.
    kind = 'post';
    const ink = [];
    const walk = (el, depth) => {
      if (depth > 24) return;
      for (const c of el.children) {
        const r = c.getBoundingClientRect();
        const st = getComputedStyle(c);
        if (!seen(r) || st.visibility === 'hidden' || st.display === 'none'
            || parseFloat(st.opacity) === 0) continue;
        if (c.matches('img, video, svg, canvas, picture, iframe')) { ink.push(r); continue; }
        let own = '';
        for (const n of c.childNodes) if (n.nodeType === 3) own += n.nodeValue;
        if (own.trim()) ink.push(r);
        walk(c, depth + 1);
      }
    };
    walk(document.body, 0);
    const face = document.body.getBoundingClientRect();
    box = ink.length ? union(ink) : { left: face.left, right: face.right, top: face.top, bottom: face.bottom };
    // Never wider or taller than the card's own page.
    box.left = Math.max(box.left, face.left); box.right = Math.min(box.right, face.right);
    box.top = Math.max(box.top, face.top);
    title = words(document.body).split('\n').filter(Boolean).slice(0, 2).join(' ');
    kept.push({ name: 'post', el: document.body });
    notes.push('card, ' + ink.length + ' painted');
  } else if (head && !(social && own)) {
    kind = 'story';
    title = words(head.el);
    const hr = head.r;
    const hw = wordsRect(head.el);
    kept.push({ name: 'headline', el: head.el, words: true });
    const left = hr.left - 60, right = hr.right + 60;
    const inColumn = r => {
      const mid = (r.left + r.right) / 2;
      return mid > left && mid < right && r.width > hr.width * 0.3;
    };

    // The body: the first real run of text under the headline, in its column.
    // Not the heaviest - a page's heaviest text is often a list of other
    // stories further down - and not the outermost, which is half the page.
    let body = null;
    for (const el of document.querySelectorAll('div, section, article, main, p')) {
      const r = el.getBoundingClientRect();
      if (!seen(r) || r.top < hr.bottom - 4 || !inColumn(r)) continue;
      if (words(el).length < 200) continue;
      if (!body || r.top < body.r.top - 2
          || (Math.abs(r.top - body.r.top) <= 2 && r.height < body.r.height)) {
        body = { el, r };
      }
    }
    // The lead picture: the first big one under the headline, and near it.
    // The whole figure where there is one, so its caption comes with it.
    let picture = null, pictureEl = null;
    // Behind the headline counts only within the page and not much wider
    // than the story's column: a wallpaper advert behind the story is behind
    // its headline too (see CLEAR_CLUTTER's lead picture).
    const pageLeft = Math.min(0, document.documentElement.clientWidth - innerWidth) - 2;
    const pageRight = Math.max(document.documentElement.clientWidth, innerWidth) + 2;
    let colW = document.documentElement.clientWidth;
    for (let e = head.el.parentElement, own = title.length; e && e !== document.documentElement; e = e.parentElement) {
      if (words(e).length - own >= 200) { colW = Math.max(e.getBoundingClientRect().width, hr.width); break; }
    }
    for (const el of document.querySelectorAll('figure, img, picture, video')) {
      const r = el.getBoundingClientRect();
      // Under the headline - or behind it: a feature story lays its headline
      // over the photo, and the cutting then starts at the photo's top.
      const under = r.top < hr.top && r.bottom >= hr.bottom - 4 && r.left <= hr.left + 4 && r.right >= hr.right - 4
        && r.left >= pageLeft && r.right <= pageRight && r.width <= colW * 1.5;
      if (seen(r) && (r.top >= hr.top - 4 || under) && r.top < hr.bottom + 1200 && inColumn(r) && area(r) > 25000) {
        const holder = el.closest('figure') || el;
        const fr = holder.getBoundingClientRect();
        const whole = seen(fr) && fr.height < r.height * 3;
        picture = whole ? fr : r;
        pictureEl = whole ? holder : el;
        break;
      }
    }
    if (pictureEl) kept.push({ name: 'picture', el: pictureEl });

    // Where the story gives way to something else - a video, an advert, a
    // "read more" strip - the cutting ends. Never at the lead picture itself,
    // and never above it.
    // Whole words (see tokens above), and a word that begins with one of the
    // longer ones: "videos", "recommended", "embedded", "widgets".
    const STOP_WORDS = new Set(['ad', 'ads', 'advert', 'adverts', 'advertisement', 'advertisements', 'alsoread',
      'adslot', 'adunit', 'adbox', 'adcontainer', 'adwrapper', 'googleads', 'gptad', 'dfp']);
    const STOP_STARTS = ['video', 'player', 'advert', 'promo', 'related', 'recommend', 'newsletter', 'trending',
      'subscribe', 'embed', 'widget'];
    let stop = 0;
    if (body) {
      for (const child of body.el.children) {
        const r = child.getBoundingClientRect();
        if (!seen(r)) continue;
        if (pictureEl && (child.contains(pictureEl) || pictureEl.contains(child))) continue;
        if (picture && r.bottom <= picture.bottom + 2) continue;
        const bad = namedAs(child, STOP_WORDS, STOP_STARTS)
          || child.querySelector('iframe, video')
          || child.tagName === 'IFRAME' || child.tagName === 'VIDEO';
        if (bad) { stop = r.top; break; }
      }
    }

    const top = Math.min(hr.top, hw.top, picture ? picture.top : hr.top);
    let bodyBottom = body ? Math.min(body.r.bottom, body.r.top + BODY_RUN) : 0;
    if (stop) bodyBottom = Math.min(bodyBottom, stop - 8);
    const bottom0 = Math.max(hr.bottom, picture ? picture.bottom : 0, bodyBottom);

    // The text lines, measured from the text itself. TOI sets its paragraphs
    // as bare text beside a floated picture: no element holds a line of its
    // own, and a cutting as narrow as the headline sliced the text.
    const lines = [], lineEls = [];
    let bottom = bottom0;
    if (body) {
      const tw = document.createTreeWalker(body.el, NodeFilter.SHOW_TEXT, { acceptNode: n =>
        (n.nodeValue.trim().length < 2 || !n.parentElement
         || n.parentElement.closest('figure, figcaption, [data-clip-hidden], [data-clip-rail], script, style, noscript, button, nav, select'))
          ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
      const range = document.createRange();
      const frags = [];
      while (tw.nextNode() && frags.length < 1500) {
        range.selectNodeContents(tw.currentNode);
        for (const r of range.getClientRects()) {
          if (!seen(r) || r.top < hr.bottom - 2 || r.top > bottom0 + 40) continue;
          const mid = (r.left + r.right) / 2;
          if (mid < hr.left - 60 || mid > hr.right + 60) continue;
          frags.push({ left: r.left, right: r.right, top: r.top, bottom: r.bottom, el: tw.currentNode.parentElement });
        }
      }
      frags.sort((a, b) => a.top - b.top);
      for (const f of frags) {
        const last = lines[lines.length - 1];
        if (last && Math.abs(f.top - last.top) <= 3) {
          last.left = Math.min(last.left, f.left); last.right = Math.max(last.right, f.right); last.bottom = Math.max(last.bottom, f.bottom);
        } else {
          lines.push({ left: f.left, right: f.right, top: f.top, bottom: f.bottom, el: f.el });
        }
      }
    }
    // The bottom never cuts a line of text in half.
    const whole = lines.filter(l => l.bottom <= bottom0 + 1);
    if (lines.length && whole.length && !(picture && picture.bottom >= bottom0 - 1)) bottom = Math.max(hr.bottom, whole[whole.length - 1].bottom + 4);
    const used = lines.filter(l => l.bottom <= bottom + 2).slice(0, 14);
    lines.length = 0;
    used.forEach(l => { lines.push(l); lineEls.push(l.el); });
    keptLines = used;
    used.slice(0, 3).forEach((l, i) => kept.push({ name: 'line' + (i + 1), el: l.el, rect: l }));

    // WIDTH: the union of what is kept, never narrower than the headline's words.
    const edges = [hw];
    if (picture) edges.push(picture);
    lines.forEach(r => edges.push(r));
    const u = union(edges);
    box = { left: u.left, right: u.right, top, bottom };

    // RAILS: what stands beside the story column, below the headline, is
    // blanked, not cropped - a crop cannot be L-shaped, and a crop at the
    // rail cut a headline centred over both columns (Economic Times).
    const anchors = [...new Set([pictureEl, ...lineEls.slice(0, 6)].filter(Boolean))];
    let col = null;
    if (anchors.length) {
      col = anchors[0];
      while (col && !anchors.every(a => col.contains(a))) col = col.parentElement;
    }
    col = col || (body && body.el);
    if (col) {
      const cr = col.getBoundingClientRect();
      for (let node = col; node && node.parentElement && node !== document.body; node = node.parentElement) {
        if (node.contains(head.el)) break;
        for (const sib of node.parentElement.children) {
          if (sib === node || sib.contains(head.el) || sib.hasAttribute('data-clip-hidden')) continue;
          const r = sib.getBoundingClientRect();
          if (!seen(r)) continue;
          const beside = r.left >= cr.right - 8 || r.right <= cr.left + 8;
          if (beside && r.top < box.bottom && r.bottom > hr.bottom - 4 && r.left < box.right && r.right > box.left) {
            setStyle(sib, 'visibility', 'hidden');
            sib.setAttribute('data-clip-rail', '1');
            rails.push(short(sib));
          }
        }
      }
    }

    // Named junk still overlapping: blank it beside the story, pull the edge
    // in only beside the headline row (never through its words), and end the
    // cutting at it only when it comes after the lead picture.
    const JUNK = new Set(['ad', 'ads', 'advert', 'adverts', 'advertisement', 'advertisements', 'sidebar', 'rail',
      'aside', 'promo', 'recommend', 'related', 'youmay', 'outbrain', 'taboola', 'newsletter', 'subscribe']);
    const holdsKept = el => kept.some(k => el.contains(k.el) || k.el.contains(el));
    for (const el of document.querySelectorAll('aside, div, section, ins, iframe')) {
      if (el.closest('[data-clip-hidden], [data-clip-rail]')) continue;
      const r = el.getBoundingClientRect();
      if (!seen(r) || r.width < 120 || r.height < 80) continue;
      if (el.tagName !== 'ASIDE' && el.tagName !== 'INS' && !namedAs(el, JUNK)) continue;
      if (holdsKept(el)) continue;
      const overlaps = r.left < box.right - 8 && r.right > box.left + 8
                    && r.top < box.bottom - 8 && r.bottom > box.top + 8;
      if (!overlaps) continue;
      if (r.left > box.left + (box.right - box.left) * 0.45) {
        if (r.top >= hr.bottom - 4) {
          setStyle(el, 'visibility', 'hidden');
          el.setAttribute('data-clip-rail', '1');
          rails.push(short(el));
        } else {
          box.right = Math.max(hw.right + 8, Math.min(box.right, r.left - 10));
          notes.push('pulled in beside the headline by ' + short(el));
        }
      } else if (r.top > Math.max(hr.bottom, picture ? picture.bottom : 0) - 4) {
        box.bottom = Math.min(box.bottom, r.top - 10);
        notes.push('ended at ' + short(el));
      }
    }
    box.left = Math.min(box.left, hw.left);
    box.right = Math.max(box.right, hw.right);
  } else if (own) {
    kind = 'post';
    const r = own.getBoundingClientRect();
    box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    title = words(own).split('\n').slice(0, 2).join(' ');
    kept.push({ name: 'post', el: own });
  } else {
    kind = 'page';
    const r = document.body.getBoundingClientRect();
    box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    // WHAT THE PAGE CALLS ITSELF. Its own <h1> first, even a short one - the
    // headline picked for the cutting had to be longer than fifteen letters
    // to be the thing a cutting is built round, but as a NAME a short one is
    // still the page's own and still better than the tab's wording. Then
    // what the page tells a site to print when it is shared (og:title), which
    // is the headline without the paper's name on the end. The tab's own
    // words last: they are the headline with " - The Times of India" after
    // it, or just the paper's name.
    const named = [...document.querySelectorAll('h1')]
      .map(el => ({ el, r: el.getBoundingClientRect() }))
      .filter(h => seen(h.r) && words(h.el))
      .sort((a, b) => area(b.r) - area(a.r))[0];
    const shared = document.querySelector(
      'meta[property="og:title"], meta[name="twitter:title"]');
    title = (named ? words(named.el) : '')
      || (shared && (shared.content || '').trim())
      || (document.title || '').trim();
  }

  // Padding last. Where the page edge eats it, the shortfall is handed back
  // as a margin to be painted in the page's own colour: a headline flush with
  // the edge (Hindustan Times) otherwise starts at the glyphs.
  const pad = 16;
  const docW = Math.max(document.documentElement.scrollWidth, document.documentElement.clientWidth);
  let x0 = box.left + scrollX - pad, x1 = box.right + scrollX + pad;
  let y0 = box.top + scrollY - pad;
  let y1 = Math.min(box.bottom + scrollY + pad, y0 + MOST_TALL);
  // Cut short at the tallest a cutting may be: the limit falls wherever it
  // falls, most often through a line of text.
  const capped = box.bottom + scrollY + pad > y0 + MOST_TALL;
  const margin = { left: Math.max(0, -x0), right: Math.max(0, x1 - docW), top: Math.max(0, -y0), bottom: 0 };
  x0 = Math.max(0, x0); x1 = Math.min(docW, x1); y0 = Math.max(0, y0);

  // The padding never shows part of a line that is not in the cutting. The
  // bottom was snapped to a whole line, but 16 pixels under it is most of the
  // next line where lines are less than 20 pixels apart - which is most body
  // text - and it came out sliced (a kicker over the headline likewise). The
  // cutting stops short of such a line and the rest of the padding is handed
  // back as margin, painted in the page's colour like the rest.
  const inTop = box.top + scrollY, inBottom = box.bottom + scrollY;
  let cutTop = y0, cutBottom = y1;
  if (inBottom < y1 || inTop > y0 || capped) {
    const edgeWalker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: n =>
      (!n.nodeValue.trim() || !n.parentElement
       || n.parentElement.closest('script, style, noscript, [data-clip-hidden], [data-clip-rail]'))
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    const edgeRange = document.createRange();
    for (let looked = 0; edgeWalker.nextNode() && looked < 20000; looked++) {
      const holder = edgeWalker.currentNode.parentElement;
      const hr2 = holder.getBoundingClientRect();
      if (hr2.bottom + scrollY <= y0 || hr2.top + scrollY >= y1 || hr2.right + scrollX <= x0 || hr2.left + scrollX >= x1) continue;
      if (getComputedStyle(holder).visibility === 'hidden') continue;
      edgeRange.selectNodeContents(edgeWalker.currentNode);
      for (const r of edgeRange.getClientRects()) {
        if (r.width < 1 || r.height < 4 || r.right + scrollX <= x0 || r.left + scrollX >= x1) continue;
        const top = r.top + scrollY, bottom = r.bottom + scrollY;
        if (top >= inBottom - 1 && top < cutBottom) cutBottom = Math.max(inBottom, top - 1);
        if (bottom <= inTop + 1 && bottom > cutTop) cutTop = Math.min(inTop, bottom + 1);
        // The line the height limit falls through is left out whole (a long
        // "page" cutting ended through the top halves of its last line).
        if (capped && top < y1 && bottom > y1 && top - 1 > y0 + 40) cutBottom = Math.min(cutBottom, top - 1);
      }
    }
  }
  margin.bottom = Math.max(0, y1 - cutBottom); y1 = cutBottom;
  margin.top += Math.max(0, cutTop - y0); y0 = cutTop;
  // The side margins are painted in the page's own colour: a photo flush with
  // the edge is not to be stretched. The top and bottom are painted in the
  // colour behind what the cutting starts and ends at - a white story card on
  // a grey page had a grey band painted under its last line.
  const background = (document.body && bgOf(document.body)) || bgOf(document.documentElement) || 'rgb(255, 255, 255)';
  let topEl = document.body, bottomEl = document.body;
  if (kind === 'story') {
    const pic = kept.find(k => k.name === 'picture');
    const head1 = kept.find(k => k.name === 'headline');
    topEl = pic && pic.el.getBoundingClientRect().top < head1.el.getBoundingClientRect().top ? pic.el : head1.el;
    let lowest = null, lowestAt = -Infinity;
    for (const l of keptLines) if (l.bottom <= box.bottom + 2 && l.bottom > lowestAt) { lowest = l.el; lowestAt = l.bottom; }
    if (pic) { const pr = pic.el.getBoundingClientRect(); if (pr.bottom <= box.bottom + 2 && pr.bottom > lowestAt) { lowest = pic.el; lowestAt = pr.bottom; } }
    bottomEl = lowest || head1.el;
  } else if (kind === 'post') {
    topEl = bottomEl = own;
  }
  const edges = { top: behind(topEl, background), bottom: behind(bottomEl, background) };
  const keptRects = kept.map(k => {
    const r = k.rect ? k.rect : (k.words ? wordsRect(k.el) : k.el.getBoundingClientRect());
    const page = { name: k.name, x: r.left + scrollX, y: r.top + scrollY, right: r.right + scrollX, bottom: r.bottom + scrollY };
    // A line is a run of text, not an element: where its element is now is
    // remembered, so CHECK_KEPT can say where the line went.
    const at = k.el.getBoundingClientRect();
    k.page = page;
    k.at = { x: at.left + scrollX, y: at.top + scrollY };
    return page;
  });
  window.__clipKept = kept;
  return JSON.stringify({
    kind, title,
    x: x0, y: y0, width: x1 - x0, height: y1 - y0,
    margin, background, edges, kept: keptRects, rails: rails.slice(0, 8), notes,
    docWidth: docW, innerWidth: innerWidth, clientWidth: document.documentElement.clientWidth,
    site: location.hostname.replace(/^www\./, ''),
    href: location.href,
    page_title: document.title || '',
    // A card with no post behind it says so in the site's own words, and
    // says it in the middle of the card rather than in its first line
    // ("Instagram / Instagram / The link to this photo may be broken"), so
    // the whole of its writing goes back and core/embedcard reads it.
    card: card || undefined,
    cardText: card ? words(document.body).slice(0, 400) : undefined,
  });
})()
"""

# ------------------------------------------------------------------- player
POSTER_FOR_PLAYER = r"""
(() => {
  /*KEEP*/
  // A lead video player that has swapped its thumbnail for a black or empty
  // frame (Economic Times, about three seconds in): a picture goes in its
  // place, the same size, from the player's own poster or the page's share
  // picture. Only when the player shows no picture of its own.
  const k = (window.__clipKept || []).find(k => k.name === 'picture');
  if (!k || !k.el || !k.el.isConnected) return 'no picture';
  const holder = k.el;
  const player = holder.matches('iframe, video') ? holder : holder.querySelector('iframe, video');
  if (!player) return 'not a player';
  const own = [...holder.querySelectorAll('img')].filter(i => { const r = i.getBoundingClientRect();
    return r.width * r.height > 20000 && i.complete && i.naturalWidth > 0 && getComputedStyle(i).visibility !== 'hidden'; });
  if (own.length) return 'has its own picture';
  const meta = document.querySelector('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"], meta[property="twitter:image"]');
  const poster = (player.tagName === 'VIDEO' && player.poster) || (meta && meta.content) || '';
  if (!poster) return 'no poster';
  const r = player.getBoundingClientRect();
  if (r.width * r.height < 20000) return 'player too small';
  const img = document.createElement('img');
  img.src = poster;
  img.setAttribute('data-clip-added', '1');
  img.setAttribute('data-clip-poster', '1');
  img.style.cssText = 'display:block;width:' + r.width + 'px;height:' + r.height + 'px;object-fit:cover;margin:0;';
  player.parentElement.insertBefore(img, player);
  setStyle(player, 'display', 'none');
  return 'poster ' + poster.slice(0, 90);
})()
"""

# --------------------------------------------------------------- the waits
#: Called as (WAIT_BLOCK)(clip, milliseconds).
WAIT_BLOCK = r"""
(async (rect, ms) => {
  /*KEEP*/
  const sleep = n => new Promise(r => setTimeout(r, n));
  const within = (p, n) => Promise.race([Promise.resolve(p).then(() => true, () => true), sleep(n).then(() => false)]);
  const inside = r => r.width * r.height > 2500 && r.left + scrollX < rect.x + rect.width && r.right + scrollX > rect.x
                    && r.top + scrollY < rect.y + rect.height && r.bottom + scrollY > rect.y;
  const pending = [];
  let late = 0;
  for (const img of document.querySelectorAll('img')) {
    if (!inside(img.getBoundingClientRect())) continue;
    if ((img.getAttribute('loading') || '').toLowerCase() === 'lazy') setAttr(img, 'loading', 'eager');
    if (img.complete && img.naturalWidth > 0) continue;
    late++;
    pending.push(img.decode ? img.decode().catch(() => {}) : sleep(ms));
  }
  const done = await within(Promise.all(pending), ms);
  const broken = [...document.querySelectorAll('img')].filter(i => inside(i.getBoundingClientRect()) && !(i.complete && i.naturalWidth > 0)).length;
  return JSON.stringify({late, done, broken});
})
"""

#: Called as (SCROLL_TO)(y). Answers where the page came to rest.
SCROLL_TO = r"""
(async (y) => {
  const sleep = n => new Promise(r => setTimeout(r, n));
  const frame = () => Promise.race([new Promise(r => requestAnimationFrame(() => r())), sleep(120)]);
  try { scrollTo({left: 0, top: y, behavior: 'instant'}); } catch (e) { scrollTo(0, y); }
  await frame(); await frame(); await sleep(150);
  return scrollY;
})
"""

CHECK_KEPT = r"""
(() => {
  const kept = (window.__clipKept || []).filter(k => k.el && k.el.isConnected);
  return JSON.stringify(kept.map(k => {
    const now = k.el.getBoundingClientRect();
    if (k.rect && k.page && k.at) {
      const dx = now.left + scrollX - k.at.x, dy = now.top + scrollY - k.at.y;
      return {name: k.name, x: k.page.x + dx, y: k.page.y + dy, right: k.page.right + dx, bottom: k.page.bottom + dy};
    }
    let r = now;
    if (k.words) { const range = document.createRange(); range.selectNodeContents(k.el);
      const rs = [...range.getClientRects()].filter(x => x.width > 2 && x.height > 2);
      if (rs.length) r = {left: Math.min(...rs.map(x => x.left)), right: Math.max(...rs.map(x => x.right)),
                          top: Math.min(...rs.map(x => x.top)), bottom: Math.max(...rs.map(x => x.bottom))};
    }
    return {name: k.name, x: r.left + scrollX, y: r.top + scrollY, right: r.right + scrollX, bottom: r.bottom + scrollY};
  }));
})()
"""

# ------------------------------------------------------------------ restore
#: Called as (RESTORE_PAGE)({x, y}) - where the page was scrolled to before.
RESTORE_PAGE = r"""
((saved) => {
  const PREV = 'data-clip-prev';
  let put = 0;
  for (const el of [...document.querySelectorAll('[data-clip-added]')]) { el.remove(); put++; }
  for (const el of [...document.querySelectorAll('[' + PREV + ']')]) {
    let was = {};
    try { was = JSON.parse(el.getAttribute(PREV) || '{}') || {}; } catch (e) { was = {}; }
    for (const attr of Object.keys(was)) {
      // Read it first. A style changed through el.style is written into the
      // attribute only when something reads it; removed unread, Chrome still
      // prints the element with style="" (measured).
      el.getAttribute(attr);
      if (was[attr] === null) el.removeAttribute(attr); else el.setAttribute(attr, was[attr]);
    }
    el.removeAttribute(PREV);
    put++;
  }
  for (const name of ['data-clip-hidden', 'data-clip-rail', 'data-clip-poster'])
    for (const el of [...document.querySelectorAll('[' + name + ']')]) el.removeAttribute(name);
  try { delete window.__clipKept; } catch (e) { window.__clipKept = undefined; }
  if (saved && typeof saved.y === 'number') {
    try { scrollTo({left: saved.x || 0, top: saved.y, behavior: 'instant'}); } catch (e) { scrollTo(saved.x || 0, saved.y); }
  }
  const left = document.querySelectorAll('[data-clip-prev], [data-clip-hidden], [data-clip-rail], [data-clip-added], [data-clip-poster]').length;
  return JSON.stringify({put, left, x: scrollX, y: scrollY});
})
"""


def _finish(script: str) -> str:
    script = script.replace("/*CARD*/", f"const CARD_PAGE = {CARD_PAGE};\n"
                            "  const card = CARD_PAGE.test(location.href);")
    return (script.replace("/*KEEP*/", _KEEP)
            .replace("BODY_RUN", str(BODY_RUN))
            .replace("MOST_TALL", str(MOST_TALL)))


STILL_THE_VIDEO = _finish(STILL_THE_VIDEO)
PREPARE_PAGE = _finish(PREPARE_PAGE)
CLEAR_CLUTTER = _finish(CLEAR_CLUTTER)
FIND_BLOCK = _finish(FIND_BLOCK)
POSTER_FOR_PLAYER = _finish(POSTER_FOR_PLAYER)
WAIT_BLOCK = _finish(WAIT_BLOCK)
