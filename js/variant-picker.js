/* A static, opt-in source for one collision group. The master is unchanged. */
(function () {
  'use strict';
  var root = document.getElementById('variantPicker');
  if (!root) return;
  var group = root.querySelector('[name="group"]'), choice = root.querySelector('[name="choice"]');
  var result = root.querySelector('[data-variant-url]'), link = root.querySelector('[data-variant-link]');
  var message = root.querySelector('[data-variant-message]'), copy = root.querySelector('[data-variant-copy]');
  var groups = [];
  function option(select, value, label) { var item = document.createElement('option'); item.value = value; item.textContent = label; select.appendChild(item); }
  function selected() {
    var item = groups[Number(group.value)], picked = item && item.choices[Number(choice.value)];
    var url = picked && /^https:\/\//.test(picked.url) ? picked.url : '';
    result.textContent = url || 'Choose an alternative.'; link.href = url || '#'; link.hidden = !url; copy.disabled = !url;
  }
  function choices() {
    choice.replaceChildren();
    var item = groups[Number(group.value)];
    if (item) item.choices.forEach(function (entry, i) { option(choice, String(i), entry.name); });
    selected();
  }
  group.addEventListener('change', choices); choice.addEventListener('change', selected);
  copy.addEventListener('click', function () {
    if (!navigator.clipboard || !navigator.clipboard.writeText) { message.textContent = 'Copy the displayed URL manually.'; return; }
    navigator.clipboard.writeText(result.textContent).then(function () { message.textContent = 'Source URL copied.'; }, function () { message.textContent = 'Copy the displayed URL manually.'; });
  });
  fetch('../feeds/variants/index.json').then(function (response) { if (!response.ok) throw new Error('unavailable'); return response.json(); }).then(function (doc) {
    groups = Array.isArray(doc.groups) ? doc.groups.filter(function (g) { return g && Array.isArray(g.choices) && g.choices.length; }) : [];
    group.replaceChildren(); groups.forEach(function (entry, i) { option(group, String(i), entry.bundleIdentifier); });
    if (!groups.length) { message.textContent = 'No shared bundle groups are listed.'; return; }
    choices();
  }).catch(function () { message.textContent = 'Variant list unavailable. Single-app feeds remain available on each app page.'; });
})();
