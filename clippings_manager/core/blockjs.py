"""The script that runs inside the page and says where the cutting is.

It runs inside the page, in the browser, and answers one question: which
rectangle is the cutting? A news page is headline-first - the headline, the
picture under it and the first inches of the story. A social post is a card of
its own. Everything that floats over the page is taken away before anything is
measured, so a cookie bar never lands across the picture.

Deliberately not tag-driven: the Times of India puts its story in plain divs
with no <p> at all, so the body is found by weight of text, not by tag name.
"""

#: How much of the story to show under the headline, in CSS pixels. Enough for
#: the picture and the opening paragraphs; a whole page prints too small.
BODY_RUN = 620
#: Nothing taller than this is ever captured, whatever the page looks like.
MOST_TALL = 2200

FIND_BLOCK = r"""
(() => {
  const HIDE = 'display';
  const seen = r => r.width > 2 && r.height > 2;
  const area = r => r.width * r.height;
  const words = el => (el.innerText || '').trim();

  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if ((s.position === 'fixed' || s.position === 'sticky') && s.display !== 'none') {
      el.style.setProperty(HIDE, 'none', 'important');
    }
  }

  // A wall instead of a page: X and Facebook show one to anybody not signed
  // in, and a picture of it is worth nothing.
  const wall = document.querySelector(
    '[data-testid="loginButton"], [data-testid="LoginForm_Login_Button"], '
    + '#login_form, [action*="/login"][method="post"]');
  const own = document.querySelector(
    'article[role="article"], [data-testid="tweet"], div[role="article"]');
  const social = /(^|\.)(x\.com|twitter\.com|facebook\.com|instagram\.com|threads\.net)$/i
    .test(location.hostname);
  if ((wall || social) && !own) {
    return JSON.stringify({
      blocked: social
        ? 'that post could not be read. Either it needs you to be signed in - press '
          + '"Take from my Chrome", or "Sign in for captures" once - or the post '
          + 'has been taken down.'
        : 'that page wants you to be signed in. Press "Take from my Chrome", or '
          + '"Sign in for captures" once and try again.',
      site: location.hostname.replace(/^www\./, ''),
    });
  }

  const post = own;
  const heads = [...document.querySelectorAll('h1')]
    .map(el => ({ el, r: el.getBoundingClientRect() }))
    .filter(h => seen(h.r) && words(h.el).length > 15)
    .sort((a, b) => area(b.r) - area(a.r));
  const head = heads[0];

  let box = null, title = '', kind = '';

  if (head) {
    kind = 'story';
    title = words(head.el);
    const hr = head.r;
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
    // The lead picture: the first big one under the headline.
    let picture = null;
    for (const el of document.querySelectorAll('figure, img, picture, video')) {
      const r = el.getBoundingClientRect();
      if (seen(r) && r.top >= hr.top - 4 && inColumn(r) && area(r) > 25000) {
        // The whole figure where there is one, so the picture's own caption
        // comes with it rather than being sliced off at the bottom edge.
        const box = el.closest('figure') || el;
        const fr = box.getBoundingClientRect();
        picture = seen(fr) && fr.height < r.height * 3 ? fr : r;
        break;
      }
    }

    // Where the story gives way to something else - a video, an advert, a
    // "read more" strip - the cutting ends, even if there is room left.
    const STOP = /(video|player|advert|ads?|promo|related|recommend|newsletter|trending|subscribe|also-read|alsoread|embed|widget)/i;
    let stop = 0;
    if (body) {
      for (const child of body.el.children) {
        const r = child.getBoundingClientRect();
        if (!seen(r)) continue;
        const bad = STOP.test(child.className + ' ' + child.id)
          || child.querySelector('iframe, video')
          || child.tagName === 'IFRAME' || child.tagName === 'VIDEO';
        if (bad) { stop = r.top; break; }
      }
    }

    const top = hr.top;
    let bodyBottom = body ? Math.min(body.r.bottom, body.r.top + BODY_RUN) : 0;
    if (stop) bodyBottom = Math.min(bodyBottom, stop - 8);
    const bottom = Math.max(hr.bottom, picture ? picture.bottom : 0, bodyBottom);
    // The width comes from what actually holds the story: the picture and the
    // first line of body text, never wider than the headline. A headline box
    // can span the whole page even when its words wrap early, and a body
    // container often reaches across the advert rail - taking either brought
    // "you may like" into the cutting.
    const lines = [];
    if (body) {
      const walk = body.el.querySelectorAll('p, div, span, li');
      for (const el of [body.el, ...walk]) {
        const r = el.getBoundingClientRect();
        if (!seen(r) || words(el).length < 60) continue;
        // Only the innermost holder of its own words, and never a picture's
        // caption - a caption is as narrow as the picture and would cut the
        // story column in half.
        if (el.children.length && [...el.children].some(c => words(c).length >= 60)) continue;
        if (el.closest('figure, figcaption')) continue;
        lines.push(r);
        if (lines.length >= 6) break;
      }
    }
    const text = lines.length
      ? { left: Math.min(...lines.map(r => r.left)),
          right: Math.max(...lines.map(r => r.right)) }
      : null;
    // How far the headline's WORDS actually reach. Its box can be the width of
    // the page while the words wrap early, and clamping to the box let the
    // advert rail in; clamping to the body column cut the headline in half.
    const range = document.createRange();
    range.selectNodeContents(head.el);
    const spans = [...range.getClientRects()].filter(seen);
    const headRight = spans.length ? Math.max(...spans.map(r => r.right)) : hr.right;
    const headLeft = spans.length ? Math.min(...spans.map(r => r.left)) : hr.left;

    const edges = [picture, text].filter(Boolean);
    const lefts = [headLeft, ...edges.map(r => r.left)];
    const rights = edges.length
      ? [Math.max(headRight, Math.min(hr.right, Math.max(...edges.map(r => r.right))))]
      : [headRight];
    box = { left: Math.min(...lefts), right: Math.max(...rights), top, bottom };
  } else if (post) {
    kind = 'post';
    const r = post.getBoundingClientRect();
    box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    title = words(post).split('\n').slice(0, 2).join(' ');
  } else {
    kind = 'page';
    const r = document.body.getBoundingClientRect();
    box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    title = (document.title || '').trim();
  }

  // Whatever the measurements said, nothing that is plainly an advert rail or
  // a "you may like" list stays in the cutting: the box is pulled in to stop
  // short of it. A page whose headline runs wider than its story column drags
  // the rail in otherwise.
  if (kind === 'story') {
    const JUNK = /(^|[^a-z])(ads?|advert|advertisement|sidebar|side-bar|rail|aside|promo|recommend|related|you-?may|outbrain|taboola|newsletter|subscribe)([^a-z]|$)/i;
    for (const el of document.querySelectorAll('aside, div, section, ins, iframe')) {
      const r = el.getBoundingClientRect();
      if (!seen(r) || r.width < 120 || r.height < 80) continue;
      const name = (el.className && el.className.baseVal !== undefined
                    ? el.className.baseVal : String(el.className || '')) + ' ' + (el.id || '');
      if (el.tagName !== 'ASIDE' && el.tagName !== 'INS' && !JUNK.test(name)) continue;
      const overlaps = r.left < box.right - 8 && r.right > box.left + 8
                    && r.top < box.bottom - 8 && r.bottom > box.top + 8;
      if (!overlaps) continue;
      if (r.left > box.left + (box.right - box.left) * 0.45) {
        box.right = Math.min(box.right, r.left - 10);   // a rail on the right
      } else if (r.top > box.top + 80) {
        box.bottom = Math.min(box.bottom, r.top - 10);  // a block in the way
      }
    }
  }

  const pad = 16;
  const width = Math.min(document.documentElement.scrollWidth,
                         box.right - box.left + pad * 2);
  const height = Math.min(MOST_TALL, box.bottom - box.top + pad * 2);
  return JSON.stringify({
    kind, title,
    x: Math.max(0, box.left + window.scrollX - pad),
    y: Math.max(0, box.top + window.scrollY - pad),
    width, height,
    site: location.hostname.replace(/^www\./, ''),
    href: location.href,
    page_title: document.title || '',
  });
})()
"""

FIND_BLOCK = (FIND_BLOCK.replace("BODY_RUN", str(BODY_RUN))
              .replace("MOST_TALL", str(MOST_TALL)))
