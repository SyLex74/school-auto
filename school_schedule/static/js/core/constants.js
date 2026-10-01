// Константы и настройки
class Constants {
    static get SUBJECTS() {
        return [
            'Математика', 'Русский язык', 'Литература', 'Физика', 'Химия',
            'Биология', 'История', 'География', 'Английский язык', 'Немецкий язык',
            'Французский язык', 'Информатика', 'Обществознание', 'Экономика',
            'Право', 'Физкультура', 'ОБЖ', 'Технология', 'Музыка', 'ИЗО',
            'МХК', 'Астрономия', 'Экология', 'Черчение', 'Профориентация',
            '--|--'
        ];
    }

    static get CLASSROOMS() {
        const classrooms = [];
        for (let i = 1; i <= 40; i++) {
            classrooms.push(`${i}`);
        }
        return classrooms.concat([
            'Спортзал', 'Актовый зал', 'Библиотека',
            'Лаборатория', 'Компьютерный класс', 'Мастерская',
            'ДИСТАНТ', 'ВЕР СТАТ'
        ]);
    }

    static get DAY_NAMES() {
        return {
            monday: 'Понедельник',
            tuesday: 'Вторник',
            wednesday: 'Среда',
            thursday: 'Четверг',
            friday: 'Пятница',
            saturday: 'Суббота'
        };
    }

    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}