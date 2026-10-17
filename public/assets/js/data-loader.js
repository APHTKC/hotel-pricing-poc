(function () {
  let manifestPromise;

  function normalize(path) {
    return String(path).replace(/^\.\//, '').split(/[?#]/, 1)[0];
  }

  function manifest() {
    if (!manifestPromise) {
      manifestPromise = fetch('./data/asset_manifest.json', { cache: 'no-cache' })
        .then(response => response.ok ? response.json() : { assets: {} })
        .catch(() => ({ assets: {} }));
    }
    return manifestPromise;
  }

  async function loadJson(path) {
    const versions = await manifest();
    const version = versions.assets?.[normalize(path)]?.sha256;
    const separator = String(path).includes('?') ? '&' : '?';
    const url = version ? `${path}${separator}v=${version}` : path;
    const response = await fetch(url, { cache: version ? 'force-cache' : 'no-cache' });
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    return response.json();
  }

  window.HotelDataLoader = { loadJson, manifest };
})();
