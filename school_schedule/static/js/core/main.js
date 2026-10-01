// Точка входа приложения
document.addEventListener('DOMContentLoaded', function() {
    console.log('Загрузка ScheduleCreator...');
    window.scheduleCreator = new ScheduleCreator();
    scheduleCreator.init();
});