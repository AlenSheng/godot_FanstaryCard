(() => {
  'use strict';
  document.documentElement.classList.add('js');
  const languageButton = document.querySelector('#language-toggle');
  const menuButton = document.querySelector('#menu-toggle');
  const header = document.querySelector('.site-header');
  const navigation = document.querySelector('#site-nav');
  let storedLanguage = 'zh';
  try { storedLanguage = localStorage.getItem('relicbound-language') || 'zh'; } catch { /* Storage can be unavailable in private contexts. */ }

  const updateMenuLabel = () => {
    if (!menuButton) return;
    const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
    const english = document.body.dataset.lang === 'en';
    menuButton.setAttribute('aria-label', english ? (isOpen ? 'Close navigation' : 'Open navigation') : (isOpen ? '关闭导航' : '打开导航'));
  };
  const setMenuOpen = (open) => {
    header?.classList.toggle('menu-open', open);
    menuButton?.setAttribute('aria-expanded', String(open));
    updateMenuLabel();
  };
  const setLanguage = (language) => {
    document.body.dataset.lang = language;
    document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
    const title = document.querySelector('title');
    document.title = title.dataset[language];
    const description = document.querySelector('meta[name="description"]');
    description.content = description.dataset[language];
    document.querySelectorAll('[data-i18n]').forEach((element) => {
      if (element.dataset[language]) element.textContent = element.dataset[language];
    });
    document.querySelectorAll('[data-alt-zh]').forEach((element) => {
      element.alt = element.getAttribute(`data-alt-${language}`);
    });
    document.querySelectorAll('[data-aria-zh]').forEach((element) => {
      element.setAttribute('aria-label', element.getAttribute(`data-aria-${language}`));
    });
    languageButton.textContent = language === 'en' ? '中文' : 'EN';
    languageButton.setAttribute('aria-label', language === 'en' ? '切换为中文' : 'Switch to English');
    updateMenuLabel();
  };
  setLanguage(storedLanguage === 'en' ? 'en' : 'zh');
  languageButton?.addEventListener('click', () => {
    const language = document.body.dataset.lang === 'zh' ? 'en' : 'zh';
    try { localStorage.setItem('relicbound-language', language); } catch { /* The current page still changes language. */ }
    setLanguage(language);
  });
  menuButton?.addEventListener('click', () => setMenuOpen(menuButton.getAttribute('aria-expanded') !== 'true'));
  navigation?.addEventListener('click', (event) => {
    if (event.target.closest('a')) setMenuOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menuButton?.getAttribute('aria-expanded') === 'true') {
      setMenuOpen(false);
      menuButton.focus();
    }
  });
  window.matchMedia('(min-width: 801px)').addEventListener('change', (event) => {
    if (event.matches) setMenuOpen(false);
  });

  const artDialog = document.querySelector('#art-dialog');
  if (artDialog) {
    const artwork = artDialog.querySelector('img');
    const caption = artDialog.querySelector('#art-caption');
    document.querySelectorAll('[data-art-src]').forEach((tile) => {
      tile.addEventListener('click', () => {
        const language = document.body.dataset.lang;
        artwork.src = tile.dataset.artSrc;
        artwork.alt = tile.querySelector('img').alt;
        caption.textContent = tile.getAttribute('data-art-title-' + language);
        artDialog.showModal();
        document.body.classList.add('art-open');
      });
    });
    artDialog.querySelector('.art-close').addEventListener('click', () => artDialog.close());
    artDialog.addEventListener('close', () => document.body.classList.remove('art-open'));
    artDialog.addEventListener('click', (event) => {
      const rect = artDialog.getBoundingClientRect();
      if (event.target === artDialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) artDialog.close();
    });
  }

  const tabs = Array.from(document.querySelectorAll('[data-class-tab]'));
  const panels = Array.from(document.querySelectorAll('[data-class-panel]'));
  if (tabs.length) {
    const selectClass = (id) => {
      const selected = tabs.some((tab) => tab.dataset.classTab === id) ? id : 'mage';
      tabs.forEach((tab) => {
        const active = tab.dataset.classTab === selected;
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.classPanel !== selected;
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', `tab-${panel.dataset.classPanel}`);
        panel.tabIndex = 0;
      });
    };
    const activate = (tab) => {
      selectClass(tab.dataset.classTab);
      if (window.location.hash !== `#${tab.dataset.classTab}`) window.location.hash = tab.dataset.classTab;
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activate(tab));
      tab.addEventListener('keydown', (event) => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = tabs.length - 1;
        else return;
        event.preventDefault();
        tabs[next].focus();
        activate(tabs[next]);
      });
    });
    window.addEventListener('hashchange', () => selectClass(window.location.hash.slice(1)));
    selectClass(window.location.hash.slice(1));
  }
})();
