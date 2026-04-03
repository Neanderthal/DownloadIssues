// Open popup.html in its own tab (not as a popup) so file pickers work.
chrome.action.onClicked.addListener(async () => {
  const url = chrome.runtime.getURL("popup.html");

  // Reuse existing tab if already open
  const tabs = await chrome.tabs.query({ url });
  if (tabs.length > 0) {
    await chrome.tabs.update(tabs[0].id, { active: true });
    await chrome.windows.update(tabs[0].windowId, { focused: true });
  } else {
    await chrome.tabs.create({ url });
  }
});
