function localDateKey(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function buildWorkweekColumns(reference = new Date()) {
  const today = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate());
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const todayKey = localDateKey(today);
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const tomorrowKey = localDateKey(tomorrow);
  return Array.from({ length: 5 }, (_, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    const key = localDateKey(date);
    const label = `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    const weekday = key === todayKey ? "今天" : key === tomorrowKey ? "明天" : new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(date);
    return [key, label, weekday];
  });
}

export function isInWorkweek(date, columns) {
  return Boolean(date && columns.length && date >= columns[0][0] && date <= columns.at(-1)[0]);
}

export function isMyInterview(record, userId) {
  return Boolean(userId && Array.isArray(record?.interviewerIds) && record.interviewerIds.includes(userId));
}
