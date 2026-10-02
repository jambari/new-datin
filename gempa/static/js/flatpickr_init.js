document.addEventListener("DOMContentLoaded", function() {
    // Date picker
    var dateEls = document.querySelectorAll(".flatpickr-date");
    if (dateEls.length > 0 && typeof flatpickr !== "undefined") {
        flatpickr(dateEls, {
            dateFormat: "Y-m-d",
            altInput: true,
            altFormat: "d F Y",
            locale: "id",
            allowInput: true,
        });
    }
    // DateTime picker
    var dtEls = document.querySelectorAll(".flatpickr-datetime");
    if (dtEls.length > 0 && typeof flatpickr !== "undefined") {
        flatpickr(dtEls, {
            enableTime: true,
            dateFormat: "Y-m-d H:i:S",
            altInput: true,
            altFormat: "d F Y  H:i:S",
            locale: "id",
            allowInput: true,
            time_24hr: true,
        });
    }
});
