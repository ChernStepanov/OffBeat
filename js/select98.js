// Keep the native select as the source of truth while drawing its popup in the page.
(() => {
  for (const select of document.querySelectorAll('select')) {
    const wrapper = document.createElement('span');
    wrapper.className = 'select98';
    select.before(wrapper);
    wrapper.append(select);
    select.classList.add('select98__native');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'select98__button';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    const list = document.createElement('div');
    list.className = 'select98__list';
    list.id = `${select.id}-listbox`;
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    button.setAttribute('aria-controls', list.id);
    const label = select.labels && select.labels[0];
    const labelText = label ? Array.from(label.childNodes).filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('') : '';
    const name = (labelText || select.getAttribute('aria-label') || select.id).trim();
    label?.addEventListener('click', event => { event.preventDefault(); button.focus(); });
    wrapper.append(button, list);
    let active = 0;
    function close() { list.hidden = true; button.setAttribute('aria-expanded', 'false'); button.removeAttribute('aria-activedescendant'); }
    function sync() {
      button.textContent = select.selectedOptions[0]?.textContent || '';
      button.setAttribute('aria-label', `${name}: ${button.textContent}`);
      button.disabled = select.disabled;
      button.title = select.title;
      list.replaceChildren();
      for (const [i, option] of Array.from(select.options).entries()) {
        const item = document.createElement('div');
        item.id = `${list.id}-${i}`;
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(option.selected));
        item.setAttribute('aria-disabled', String(option.disabled));
        item.textContent = option.textContent;
        item.addEventListener('click', () => choose(i));
        list.append(item);
      }
      active = Math.max(0, select.selectedIndex);
      if (select.disabled) close();
    }
    function highlight(i) {
      const options = Array.from(select.options);
      if (!options.length) return;
      i = Math.max(0, Math.min(options.length - 1, i));
      const direction = i >= active ? 1 : -1;
      while (options[i]?.disabled && i >= 0 && i < options.length) i += direction;
      if (!options[i] || options[i].disabled) return;
      active = i;
      Array.from(list.children).forEach((node, index) => node.classList.toggle('is-active', index === active));
      button.setAttribute('aria-activedescendant', list.children[active].id);
      list.children[active].scrollIntoView({block:'nearest'});
    }
    function open() { if (button.disabled) return; sync(); list.hidden = false; button.setAttribute('aria-expanded', 'true'); highlight(active); }
    function choose(i) {
      if (!select.options[i] || select.options[i].disabled) return;
      const changed = select.selectedIndex !== i;
      select.selectedIndex = i;
      close(); sync(); button.focus();
      if (changed) select.dispatchEvent(new Event('change', {bubbles:true}));
    }
    button.addEventListener('click', () => list.hidden ? open() : close());
    button.addEventListener('keydown', event => {
      if (event.key === 'Escape') { close(); return; }
      if (event.key === 'Tab') { close(); return; }
      if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
        event.preventDefault();
        if (list.hidden) open();
        else highlight(event.key === 'Home' ? 0 : event.key === 'End' ? select.options.length - 1 : active + (event.key === 'ArrowDown' ? 1 : -1));
      } else if ((event.key === 'Enter' || event.key === ' ') && !list.hidden) {
        event.preventDefault(); choose(active);
      }
    });
    document.addEventListener('pointerdown', event => { if (!wrapper.contains(event.target)) close(); });
    select.addEventListener('change', sync);
    select.addEventListener('ob:select-sync', sync);
    new MutationObserver(sync).observe(select, {childList:true, subtree:true, characterData:true, attributes:true});
    sync();
  }
})();
