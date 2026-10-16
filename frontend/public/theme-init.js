// Apply the saved theme before first paint (avoids a light flash in dark mode).
// A separate file rather than an inline script, so the Content-Security-Policy can forbid inline scripts.
;(function () {
  try {
    var pref = localStorage.getItem('jacklyn.theme') || 'system'
    var dark = pref === 'dark' || (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
    document.documentElement.classList.toggle('dark', dark)
  } catch {
    // Storage blocked: keep the default (light) theme.
  }
})()
