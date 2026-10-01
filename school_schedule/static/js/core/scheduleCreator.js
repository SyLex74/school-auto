// Основной класс приложения
class ScheduleCreator {
    constructor() {
        this.constants = Constants;
        this.classManager = new ClassManager();
        this.conflictManager = new ConflictManager();
        this.uiManager = new UIManager(this.classManager, this.conflictManager);
        this.exportManager = new ExportManager();

        this.currentUser = null;
        this.editingScheduleId = null;
    }

    init() {
        console.log('Инициализация ScheduleCreator');
        this.uiManager.setupUI();
    }

    // Методы для глобального доступа (если нужны)
    get currentDay() {
        return this.uiManager.currentDay;
    }
}