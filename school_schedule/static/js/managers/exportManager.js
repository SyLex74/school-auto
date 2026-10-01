// Экспорт данных в Excel
class ExportManager {
    constructor() {}

    exportToExcel(schedule) {
        try {
            if (typeof XLSX === 'undefined') {
                alert('Библиотека для экспорта не загружена');
                return;
            }

            const dayName = Constants.DAY_NAMES[schedule.day] || schedule.day;
            const exportData = [];

            // Заголовок
            exportData.push([dayName]);

            // Определяем все классы в правильном порядке
            const classNames = schedule.classes.map(c => c.name);

            // Заголовок таблицы
            exportData.push(['Урок', ...classNames]);

            // Находим максимальное количество уроков среди всех классов
            let maxLessons = 0;
            schedule.classes.forEach(c => {
                if (c.lessons.length > maxLessons) {
                    maxLessons = c.lessons.length;
                }
            });

            // Заполняем уроки по горизонтали
            for (let lessonNum = 0; lessonNum < maxLessons; lessonNum++) {
                const lessonRow = [lessonNum + 1]; // Номер урока

                schedule.classes.forEach(classObj => {
                    const lesson = classObj.lessons[lessonNum];
                    let cellValue = '';

                    if (lesson) {
                        if (lesson.subject === '--|--') {
                            cellValue = '';
                        } else if (lesson.subject) {
                            const subject = lesson.subject;

                            let classrooms = '';
                            if (lesson.classrooms && lesson.classrooms.length > 0) {
                                classrooms = lesson.classrooms.map(c => {
                                    if (typeof c === 'object') {
                                        return c.type ? `${c.classroom}(${c.type})` : c.classroom;
                                    } else {
                                        return c;
                                    }
                                }).join('/');
                            }

                            if (classrooms) {
                                cellValue = `${subject} ${classrooms}`;
                            } else {
                                cellValue = subject;
                            }
                        }
                    }

                    lessonRow.push(cellValue);
                });

                exportData.push(lessonRow);
            }

            // Создаем рабочий лист
            const ws = XLSX.utils.aoa_to_sheet(exportData);

            // Настраиваем ширину столбцов
            const colWidths = [{ wch: 8 }];
            for (let i = 0; i < classNames.length; i++) {
                colWidths.push({ wch: 25 });
            }
            ws['!cols'] = colWidths;

            // Создаем рабочую книгу
            const wb = XLSX.utils.book_new();
            const sheetName = 'ДЕНЬ ПЕРВЫЙ';
            XLSX.utils.book_append_sheet(wb, ws, sheetName);

            // Генерируем имя файла
            const dateStr = new Date().toISOString().split('T')[0];
            const fileName = `расписание_${dateStr}.xlsx`;

            // Сохраняем файл
            XLSX.writeFile(wb, fileName);
            console.log('Файл экспортирован:', fileName);

            // Показываем сообщение об успехе
            this.showSuccessMessage();

        } catch (error) {
            console.error('Ошибка при экспорте в Excel:', error);
            alert('Произошла ошибка при экспорте файла. Попробуйте еще раз.');
        }
    }

    showSuccessMessage() {
        const message = document.createElement('div');
        message.className = 'success-message';
        message.innerHTML = `
            <div class="success-content">
                <span class="success-icon">✅</span>
                <div class="success-text">
                    <h3>Расписание успешно скачано!</h3>
                    <p>Файл сохранен в формате расписание.xlsx</p>
                </div>
            </div>
        `;

        document.body.appendChild(message);

        const style = document.createElement('style');
        style.textContent = `
            .success-message {
                position: fixed;
                top: 20px;
                right: 20px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                padding: 20px;
                z-index: 3000;
                animation: slideInRight 0.5s ease-out;
                border-left: 5px solid #4CAF50;
                max-width: 350px;
            }
            .success-content {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            .success-icon {
                font-size: 32px;
                color: #4CAF50;
            }
            .success-text h3 {
                margin: 0 0 5px 0;
                color: #2e7d32;
            }
            .success-text p {
                margin: 0;
                color: #666;
            }
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOutRight {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);

        setTimeout(() => {
            message.style.animation = 'slideOutRight 0.5s ease-out forwards';
            setTimeout(() => {
                message.remove();
                style.remove();
            }, 500);
        }, 5000);
    }
}