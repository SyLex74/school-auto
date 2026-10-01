// scheduleGenerator.js
// Расширенный генератор с поддержкой предпочтений по дням и привязки кабинетов к предметам

class ScheduleGenerator {
    /**
     * @param {Object} template - шаблон расписания
     * @param {string} dayKey - день недели (monday, tuesday...)
     * @param {Object} dayNamesMap - словарь названий дней
     */
    constructor(template, dayKey, dayNamesMap) {
        this.template = template;
        this.dayKey = dayKey;
        this.dayNames = dayNamesMap;
        this.classes = template.classes || [];
        // subjects теперь могут содержать preferredClassrooms
        this.subjects = template.subjects || [];
        this.classrooms = template.classrooms || [];
        this.classSubjectHours = template.classSubjectHours || [];
        this.daysOrder = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    }

    // ========== Публичные методы ==========
    
    /** Генерация расписания для одного дня */
    generate() {
        const lessonsPerClass = this.getLessonsForDay();
        const withClassrooms = this.assignClassrooms(lessonsPerClass);
        return this.formatResult(withClassrooms);
    }

    /** Генерация расписания на всю неделю */
    generateFullWeek() {
        const weekSchedule = {};
        for (let day of this.daysOrder) {
            // Временно подменяем dayKey для текущего дня
            const originalDayKey = this.dayKey;
            this.dayKey = day;
            const lessonsPerClass = this.getLessonsForDay();
            const withClassrooms = this.assignClassrooms(lessonsPerClass);
            weekSchedule[day] = this.formatResult(withClassrooms);
            this.dayKey = originalDayKey;
        }
        return weekSchedule;
    }

    // ========== Внутренние методы ==========

    /**
     * Распределение часов по дням с учётом preferredDays
     * Возвращает { className: [subject1, subject2, ...] } для текущего дня
     */
    getLessonsForDay() {
        const result = {};
        const dayIndex = this.daysOrder.indexOf(this.dayKey);
        if (dayIndex === -1) return result;

        for (let cls of this.classes) {
            const className = cls.name;
            const subjectsMap = new Map(); // subject -> { total, daysArray }
            
            // Собираем информацию по предметам для этого класса
            const hoursForClass = this.classSubjectHours.filter(h => h.className === className);
            for (let item of hoursForClass) {
                const subjectName = item.subjectName;
                const totalHours = item.hoursPerWeek;
                let preferredDays = item.preferredDays || null; // массив дней или null
                if (preferredDays && !preferredDays.length) preferredDays = null;
                subjectsMap.set(subjectName, { total: totalHours, days: preferredDays });
            }

            const dayLessons = [];
            for (let [subject, info] of subjectsMap.entries()) {
                let daysToUse = info.days ? info.days : this.daysOrder;
                // Если предпочтительные дни заданы, но текущий день не входит в них – пропускаем
                if (info.days && !info.days.includes(this.dayKey)) continue;
                
                // Количество уроков для текущего дня
                let lessonsToday = 0;
                if (info.days) {
                    // Равномерно распределяем часы только по указанным дням
                    const daysCount = info.days.length;
                    lessonsToday = Math.floor(info.total / daysCount);
                    const remainder = info.total % daysCount;
                    const dayPosInPreferred = info.days.indexOf(this.dayKey);
                    if (dayPosInPreferred !== -1 && dayPosInPreferred < remainder) lessonsToday++;
                } else {
                    // Равномерно по всем дням недели
                    lessonsToday = Math.floor(info.total / this.daysOrder.length);
                    const remainder = info.total % this.daysOrder.length;
                    if (dayIndex < remainder) lessonsToday++;
                }
                
                for (let i = 0; i < lessonsToday; i++) {
                    dayLessons.push(subject);
                }
            }
            // Перемешиваем порядок уроков в этом дне
            result[className] = this.shuffleArray(dayLessons);
        }
        return result;
    }

    /** Перемешивание массива (Fisher-Yates) */
    shuffleArray(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    /**
     * Назначение кабинетов для всех классов в текущем дне
     * @param {Object} lessonsPerClass - { className: [subject, subject, ...] }
     * @returns {Object} { className: [{ subject, classroom }] }
     */
    assignClassrooms(lessonsPerClass) {
        // Определяем максимальное количество уроков среди классов
        let maxLessons = 0;
        for (let cls of this.classes) {
            const lessons = lessonsPerClass[cls.name] || [];
            maxLessons = Math.max(maxLessons, lessons.length);
        }

        const result = {};
        for (let cls of this.classes) {
            result[cls.name] = [];
        }

        // Обрабатываем каждый временной слот (урок №1, №2, ...)
        for (let slot = 0; slot < maxLessons; slot++) {
            const slotLessons = [];
            for (let cls of this.classes) {
                const lessons = lessonsPerClass[cls.name] || [];
                if (slot < lessons.length) {
                    const subjectName = lessons[slot];
                    slotLessons.push({
                        className: cls.name,
                        subject: subjectName,
                        preferredClassrooms: this.getPreferredClassrooms(subjectName)
                    });
                }
            }
            const assigned = this.assignClassroomsForSlot(slotLessons);
            for (let item of assigned) {
                result[item.className].push({
                    subject: item.subject,
                    classroom: item.classroom
                });
            }
        }
        return result;
    }

    /** Получение списка предпочтительных кабинетов для предмета */
    getPreferredClassrooms(subjectName) {
        const subject = this.subjects.find(s => s.name === subjectName);
        if (subject && subject.preferredClassrooms && subject.preferredClassrooms.length) {
            return subject.preferredClassrooms;
        }
        // Если у предмета нет привязки – возвращаем все кабинеты из шаблона
        return this.classrooms.map(c => c.name);
    }

    /**
     * Назначение кабинетов для одного временного слота (жадный алгоритм с сортировкой по ограничениям)
     * @param {Array} lessons - массив объектов { className, subject, preferredClassrooms }
     * @returns {Array} назначенные уроки с полем classroom
     */
    assignClassroomsForSlot(lessons) {
        // Для каждого урока вычисляем реально доступные кабинеты (не занятые в этом слоте)
        const usedInSlot = new Set();
        const withOptions = lessons.map(lesson => {
            const available = lesson.preferredClassrooms.filter(room => !usedInSlot.has(room));
            return { ...lesson, availableRooms: available };
        });
        // Сортируем по возрастанию количества вариантов (самые ограниченные первыми)
        withOptions.sort((a, b) => a.availableRooms.length - b.availableRooms.length);
        
        const assigned = [];
        for (let lesson of withOptions) {
            let chosen = null;
            // Пытаемся взять первый свободный из доступных
            for (let room of lesson.availableRooms) {
                if (!usedInSlot.has(room)) {
                    chosen = room;
                    break;
                }
            }
            // Если не нашли, ищем любой свободный кабинет из всех существующих
            if (!chosen) {
                const allRooms = this.classrooms.map(c => c.name);
                for (let room of allRooms) {
                    if (!usedInSlot.has(room)) {
                        chosen = room;
                        break;
                    }
                }
            }
            assigned.push({
                className: lesson.className,
                subject: lesson.subject,
                classroom: chosen
            });
            if (chosen) usedInSlot.add(chosen);
        }
        return assigned;
    }

    /** Форматирование результата для фронтенда */
    formatResult(withClassrooms) {
        const classesResult = [];
        for (let cls of this.classes) {
            const lessonsList = withClassrooms[cls.name] || [];
            const lessonsFormatted = lessonsList.map(l => ({
                subject: l.subject,
                classrooms: l.classroom ? [{ classroom: l.classroom, type: '' }] : []
            }));
            classesResult.push({
                id: `auto_${cls.name}_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
                name: cls.name,
                lessons: lessonsFormatted
            });
        }
        return classesResult;
    }
}