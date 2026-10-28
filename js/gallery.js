/**
 * Gallery slideshow
 * Handles image navigation with fade transition and thumbnail scrolling
 */
(function() {
  'use strict';

  const mainImg = document.getElementById('gallery-main-img');
  const thumbs = document.querySelectorAll('.gallery-thumb');
  const prevBtn = document.querySelector('.gallery-nav.prev');
  const nextBtn = document.querySelector('.gallery-nav.next');
  const status = document.getElementById('gallery-status');
  
  if (!mainImg || !thumbs.length || !prevBtn || !nextBtn) return;

  let currentIndex = 0;
  let pendingSwap = null;
  const totalImages = thumbs.length;

  // <source> wins over img.src, so the whole <picture> has to be updated.
  // Each thumbnail carries the photo's srcsets, every size it comes in, which
  // scripts/build.py writes; the main image's sizes stay as they are.
  const picture = mainImg.closest('picture');

  function showImage(thumb) {
    if (picture) {
      picture.querySelectorAll('source').forEach(source => {
        source.srcset = source.type === 'image/avif' ? thumb.dataset.avif : thumb.dataset.webp;
      });
    }
    mainImg.src = thumb.dataset.src;
  }

  /**
   * Update the main image with fade transition.
   * currentIndex moves before the timeout — clicking faster than the fade used
   * to queue callbacks that each read a stale index and stranded 'active'.
   */
  function updateImage(index) {
    if (index === currentIndex) return;

    clearTimeout(pendingSwap);

    thumbs[currentIndex].classList.remove('active');
    thumbs[currentIndex].removeAttribute('aria-current');
    thumbs[index].classList.add('active');
    thumbs[index].setAttribute('aria-current', 'true');
    currentIndex = index;

    // The new photo is otherwise silent to a screen reader: the main image's
    // alt changes, but nothing says so.
    if (status) status.textContent = `${thumbs[index].dataset.alt} (${index + 1}/${totalImages})`;

    // Fade out
    mainImg.classList.add('fade');

    // Swap the source once the fade has played
    pendingSwap = setTimeout(() => {
      pendingSwap = null;
      const thumb = thumbs[index];
      showImage(thumb);
      mainImg.alt = thumb.dataset.alt;
      mainImg.classList.remove('fade');

      thumb.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'center'
      });
    }, 400);
  }

  /**
   * Navigate to next image
   */
  function nextImage() {
    const nextIndex = (currentIndex + 1) % totalImages;
    updateImage(nextIndex);
  }

  /**
   * Navigate to previous image
   */
  function prevImage() {
    const prevIndex = (currentIndex - 1 + totalImages) % totalImages;
    updateImage(prevIndex);
  }

  // Thumbnail click handlers
  thumbs.forEach((thumb, index) => {
    thumb.addEventListener('click', () => updateImage(index));
  });

  // Navigation button handlers
  prevBtn.addEventListener('click', prevImage);
  nextBtn.addEventListener('click', nextImage);

  // Arrow keys work whenever the gallery is on screen, not only while one of
  // its buttons has focus, so the listener sits on the document and is scoped
  // by hand.
  const gallery = mainImg.closest('.info-gallery-section') || mainImg.parentElement;

  function isTyping() {
    const el = document.activeElement;
    if (!el) return false;
    return el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
  }

  function galleryOnScreen() {
    const r = gallery.getBoundingClientRect();
    return r.bottom > 0 && r.top < (window.innerHeight || document.documentElement.clientHeight);
  }

  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (isTyping() || !galleryOnScreen()) return;

    e.preventDefault();
    if (e.key === 'ArrowLeft') prevImage();
    else nextImage();
  });
})();
