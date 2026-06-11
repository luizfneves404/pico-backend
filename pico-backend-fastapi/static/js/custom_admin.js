$(document).ready(function () {
  // 1. Unbind the default SQLAdmin action handler to prevent the GET request.
  // We target the same selector SQLAdmin uses: [id^='action-custom-']
  $(document).off("click", "[id^='action-custom-']");

  // 2. Bind our new POST-based handler to the same selector.
  // This now handles both regular custom actions and modal confirmation buttons.
  $(document).on("click", "[id^='action-custom-']", function (event) {
    event.preventDefault(); // Prevent default link navigation

    var pks = [];
    $(".select-box:checked").each(function () {
      // .siblings().get(0).value gets the hidden input with the PK
      pks.push($(this).siblings().get(0).value);
    });

    window.location.href = $(this).attr("data-url") + "?pks=" + pks.join(",");
  });

  // 3. Add a new handler specifically for our "Select All" button.
  $(document).on("click", "#action-select-all-post", function (event) {
    event.preventDefault();

    const confirmation = $(this).data("confirmation");
    if (
      confirm(
        confirmation ||
          "Are you sure you want to apply this action to ALL items?"
      )
    ) {
      window.location.href = $(this).attr("data-url") + "?pks=__all__";
    }
  });
});
