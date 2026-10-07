(function () {
  const labels = {
    zh: "官方房數",
    en: "Official room count",
    ja: "公式客室数",
  };

  function localizedRoomName(room) {
    if (lang === "zh") return room.name_zh || room.name_en || room.name_ja || "";
    if (lang === "ja") return room.name_ja || room.name_en || room.name_zh || "";
    return room.name_en || room.name_zh || room.name_ja || "";
  }

  function addOfficialRoomCounts() {
    const table = document.querySelector("#detail .room-table table");
    const profile = profiles.get(selectedId);
    if (!table || !profile?.room_snapshot?.rooms) return;

    const counts = new Map(
      profile.room_snapshot.rooms
        .filter((room) => Number.isInteger(room.room_count) && room.room_count >= 0)
        .map((room) => [localizedRoomName(room).trim(), room.room_count]),
    );
    const headerRow = table.tHead?.rows?.[0];
    if (!headerRow || headerRow.querySelector("[data-official-room-count]")) return;

    const header = document.createElement("th");
    header.className = "num";
    header.dataset.officialRoomCount = "";
    header.textContent = labels[lang] || labels.en;
    headerRow.insertBefore(header, headerRow.cells[2] || null);

    [...table.tBodies[0].rows].forEach((row) => {
      const cell = document.createElement("td");
      cell.className = "num";
      const count = counts.get(row.cells[0]?.textContent.trim());
      cell.textContent = Number.isInteger(count) ? count.toLocaleString(locale[lang]) : "—";
      row.insertBefore(cell, row.cells[2] || null);
    });
  }

  const renderDetailWithoutRoomCounts = renderDetail;
  renderDetail = function () {
    renderDetailWithoutRoomCounts();
    addOfficialRoomCounts();
  };
})();
