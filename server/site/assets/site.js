(() => {
  const button = document.querySelector('#language-toggle');
  const storedLanguage = localStorage.getItem('relicbound-language');
  const setLanguage = (language) => {
    const isEnglish = language === 'en';
    document.body.dataset.lang = language;
    document.documentElement.lang = isEnglish ? 'en' : 'zh-CN';
    document.title = isEnglish ? 'Relicbound · Official Website' : 'Relicbound · 遗境行者';
    document.querySelector('meta[name="description"]').content = isEnglish
      ? 'Relicbound: a dark fantasy card roguelite shaped by relics and choices.'
      : 'Relicbound 遗境行者：一场由卡牌、遗物与抉择编织的暗黑奇幻冒险。';
    document.querySelectorAll('[data-i18n]').forEach((element) => { element.textContent = element.dataset[language]; });
    document.querySelectorAll('[data-i18n-html]').forEach((element) => { element.innerHTML = element.dataset[language]; });
    document.querySelectorAll('[data-alt-zh]').forEach((element) => { element.alt = element.dataset[`alt${language[0].toUpperCase()}${language.slice(1)}`]; });
    button.textContent = isEnglish ? '中文' : 'EN';
    button.setAttribute('aria-label', isEnglish ? '切换为中文' : 'Switch to English');
  };
  setLanguage(storedLanguage === 'en' ? 'en' : 'zh');
  button.addEventListener('click', () => {
    const nextLanguage = document.body.dataset.lang === 'zh' ? 'en' : 'zh';
    localStorage.setItem('relicbound-language', nextLanguage);
    setLanguage(nextLanguage);
  });
})();
