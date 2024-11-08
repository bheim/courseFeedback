chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "courseInfo") {
        console.log("Received course information:", message.data);
        sendResponse({ message: "Data received in background" });
    }
});