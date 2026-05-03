(function () {
    function initializeDependentAnswerSelect(preview) {
        const questionFieldId = preview.dataset.questionFieldId;
        const answerFieldId = preview.dataset.answerFieldId;
        const answerChoicesId = preview.dataset.answerChoicesId;
        if (!questionFieldId || !answerFieldId || !answerChoicesId) {
            return;
        }

        const questionField = document.getElementById(questionFieldId);
        const answerField = document.getElementById(answerFieldId);
        const answerChoicesElement = document.getElementById(answerChoicesId);
        if (!questionField || !answerField || !answerChoicesElement) {
            return;
        }

        const answerChoicesByQuestion = JSON.parse(answerChoicesElement.textContent || "{}");

        const updateAnswerChoices = () => {
            const questionValue = questionField.value;
            const currentValue = answerField.value;
            const answerChoices = answerChoicesByQuestion[questionValue] || [];

            answerField.innerHTML = "";
            answerChoices.forEach(([value, label]) => {
                const option = document.createElement("option");
                option.value = value;
                option.textContent = label;
                if (value === currentValue) {
                    option.selected = true;
                }
                answerField.appendChild(option);
            });

            if (!answerField.value && answerChoices.length) {
                answerField.value = answerChoices[0][0];
            }
        };

        questionField.addEventListener("change", updateAnswerChoices);
        updateAnswerChoices();
    }

    function initializePreview(preview) {
        const formId = preview.dataset.formId;
        const previewUrl = preview.dataset.previewUrl;
        const errorMessage = preview.dataset.previewErrorMessage || "Preview could not be loaded.";
        const seedFieldId = preview.dataset.seedFieldId;
        const form = document.getElementById(formId);
        const extraParams = {};
        if (!form || !previewUrl) {
            return;
        }

        let timer = null;

        const loadPreview = () => {
            const data = new FormData(form);
            data.delete("csrfmiddlewaretoken");
            const params = new URLSearchParams();
            for (const [key, value] of data.entries()) {
                params.append(key, value);
            }
            Object.entries(extraParams).forEach(([key, value]) => {
                params.set(key, value);
            });

            fetch(`${previewUrl}?${params.toString()}`, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then((response) => response.json())
                .then((payload) => {
                    preview.innerHTML = payload.html;
                    if (seedFieldId && payload.seed) {
                        const seedField = document.getElementById(seedFieldId);
                        if (seedField) {
                            seedField.value = payload.seed;
                        }
                    }
                })
                .catch(() => {
                    preview.innerHTML = `<div class="alert alert-warning">${errorMessage}</div>`;
                });
        };

        const schedulePreview = () => {
            if (timer) {
                window.clearTimeout(timer);
            }
            timer = window.setTimeout(loadPreview, 150);
        };

        const resetPagingAndSchedulePreview = () => {
            Object.keys(extraParams).forEach((key) => {
                delete extraParams[key];
            });
            schedulePreview();
        };

        form.querySelectorAll("select, input").forEach((field) => {
            if (field.type === "submit") {
                return;
            }
            field.addEventListener("change", resetPagingAndSchedulePreview);
        });

        preview.addEventListener("click", (event) => {
            const trigger = event.target.closest("[data-preview-page-key]");
            if (!trigger) {
                return;
            }
            event.preventDefault();
            extraParams[trigger.dataset.previewPageKey] = trigger.dataset.previewPageValue;
            loadPreview();
        });

        loadPreview();
    }

    function initialize() {
        document.querySelectorAll(".waitlist-manager-preview").forEach((preview) => {
            initializeDependentAnswerSelect(preview);
            initializePreview(preview);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize);
    } else {
        initialize();
    }
}());
