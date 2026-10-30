(async () => {
  'use strict';
  document.documentElement.classList.add('js');
  const previousLanguageButton = document.querySelector('#language-toggle');
  const languageButton = previousLanguageButton instanceof HTMLSelectElement ? previousLanguageButton : document.createElement('select');
  languageButton.id = 'language-toggle';
  languageButton.className = 'language-toggle';
  languageButton.disabled = true;
  languageButton.setAttribute('aria-busy', 'true');
  const languageRegistry = new Map([['zh', {code: 'zh', name: '简体中文'}], ['en', {code: 'en', name: 'English'}]]);
  for (const option of languageButton.options) {
    if (/^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$/.test(option.value)) languageRegistry.set(option.value, {code: option.value, name: option.text});
  }
  try {
    const response = await fetch('/assets/locales/manifest.json');
    if (response.ok) {
      for (const entry of (await response.json()).languages || []) {
        if (/^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$/.test(entry.code) && typeof entry.name === 'string' && entry.name.trim()) languageRegistry.set(entry.code, entry);
      }
    }
  } catch { /* The original languages remain available when offline. */ }
  const languages = [...languageRegistry.values()];
  languageButton.replaceChildren(...languages.map(entry => new Option(entry.name, entry.code)));
  if (previousLanguageButton !== languageButton) previousLanguageButton?.replaceWith(languageButton);
  const languageStatus = document.createElement('span');
  languageStatus.className = 'language-status';
  languageStatus.setAttribute('role', 'status');
  languageStatus.setAttribute('aria-live', 'polite');
  languageButton.after(languageStatus);
  const packs = new Map();
  let activePack = {};
  let requestedLanguage = 0;
  const menuButton = document.querySelector('#menu-toggle');
  const header = document.querySelector('.site-header');
  const navigation = document.querySelector('#site-nav');
  let storedLanguage = 'zh';
  try { storedLanguage = localStorage.getItem('relicbound-language') || 'zh'; } catch { /* Storage can be unavailable in private contexts. */ }

  const updateMenuLabel = () => {
    if (!menuButton) return;
    const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
    const key = isOpen ? 'Close navigation' : 'Open navigation';
    menuButton.setAttribute('aria-label', document.body.dataset.lang === 'zh' ? (isOpen ? '关闭导航' : '打开导航') : (activePack[key] || key));
  };
  const setMenuOpen = (open) => {
    header?.classList.toggle('menu-open', open);
    menuButton?.setAttribute('aria-expanded', String(open));
    updateMenuLabel();
  };
  const routeWithoutLocale = (path) => {
    for (const entry of languages) {
      if (!['zh', 'en'].includes(entry.code) && path.startsWith('/' + entry.code + '/')) return path.slice(entry.code.length + 1);
    }
    return path;
  };
  const setLanguage = async (language, remember = false) => {
    if (!languages.some(entry => entry.code === language)) return;
    const request = ++requestedLanguage;
    let pack = {};
    languageStatus.textContent = '';
    try {
      if (!['zh', 'en'].includes(language)) {
        if (!packs.has(language)) {
          const response = await fetch('/assets/locales/' + encodeURIComponent(language) + '.json');
          if (!response.ok) throw new Error('Locale not available');
          packs.set(language, await response.json());
        }
        pack = packs.get(language);
      }
    } catch {
      if (request !== requestedLanguage) return;
      languageButton.value = document.body.dataset.lang;
      languageStatus.textContent = activePack['Translation unavailable. Please try again.'] || 'Translation unavailable. Please try again.';
      return;
    }
    if (request !== requestedLanguage) return;
    activePack = pack.messages || {};
    const translate = (english, chinese) => language === 'zh' ? chinese : (activePack[english] || english);
    document.body.dataset.lang = language;
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : language;
    document.documentElement.dir = pack.direction || 'ltr';
    const title = document.querySelector('title');
    document.title = translate(title.dataset.en, title.dataset.zh);
    const description = document.querySelector('meta[name="description"]');
    description.content = translate(description.dataset.en, description.dataset.zh);
    document.querySelectorAll('[data-i18n]').forEach((element) => {
      element.textContent = translate(element.dataset.en, element.dataset.zh);
    });
    document.querySelectorAll('[data-alt-zh]').forEach((element) => {
      element.alt = translate(element.dataset.altEn, element.dataset.altZh);
    });
    document.querySelectorAll('[data-aria-zh]').forEach((element) => {
      element.setAttribute('aria-label', translate(element.dataset.ariaEn, element.dataset.ariaZh));
    });
    document.querySelectorAll('[data-l10n-extra]').forEach(element => {
      element.textContent = translate(element.dataset.l10nExtra, element.dataset.l10nExtra);
    });
    languageButton.value = language;
    languageButton.setAttribute('aria-label', language === 'zh' ? '语言' : (activePack.Language || 'Language'));
    document.querySelectorAll('a[href]').forEach(link => {
      const url = new URL(link.getAttribute('href'), location.href);
      if (url.origin !== location.origin || !['/', '/index.html', '/classes.html', '/seasons.html'].includes(routeWithoutLocale(url.pathname))) return;
      url.pathname = routeWithoutLocale(url.pathname);
      if (!['zh', 'en'].includes(language)) url.pathname = '/' + language + url.pathname;
      url.searchParams.delete('lang');
      if (language === 'en') url.searchParams.set('lang', 'en');
      link.setAttribute('href', url.pathname + url.search + url.hash);
    });
    const current = new URL(location.href);
    current.pathname = routeWithoutLocale(current.pathname);
    current.searchParams.delete('lang');
    if (!['zh', 'en'].includes(language)) current.pathname = '/' + language + current.pathname;
    else current.searchParams.set('lang', language);
    history.replaceState(null, '', current.pathname + current.search + current.hash);
    if (remember) try { localStorage.setItem('relicbound-language', language); } catch { /* The current page still changes language. */ }
    document.documentElement.dataset.localeReady = language;
    updateMenuLabel();
  };
  const pathLocale = location.pathname.split('/')[1];
  const queryLocale = new URL(location.href).searchParams.get('lang');
  const initialLanguage = [queryLocale === 'zh-CN' ? 'zh' : queryLocale, pathLocale, storedLanguage, document.body.dataset.lang].find(code => languages.some(entry => entry.code === code)) || 'zh';
  await setLanguage(initialLanguage);
  languageButton?.addEventListener('change', () => {
    void setLanguage(languageButton.value, true);
  });
  languageButton.disabled = false;
  languageButton.removeAttribute('aria-busy');
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
        caption.textContent = language === 'zh' ? tile.dataset.artTitleZh : (activePack[tile.dataset.artTitleEn] || tile.dataset.artTitleEn);
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
