// Управление конфликтами кабинетов
class ConflictManager {
    constructor() {
        this.classroomConflicts = new Map();
        this.pendingSelection = null;
    }

    checkConflictForLesson(currentClassId, lessonIndex, lesson, allClasses) {
        if (!lesson.classrooms || lesson.classrooms.length === 0) {
            return false;
        }

        for (const classroomObj of lesson.classrooms) {
            const classroom = typeof classroomObj === 'object' ? classroomObj.classroom : classroomObj;
            if (classroom && classroom !== 'ДИСТАНТ' && classroom !== 'ВЕР СТАТ') {
                const conflicts = this.getConflictInfo(currentClassId, lessonIndex, classroom, allClasses);
                if (conflicts.length > 0) {
                    return true;
                }
            }
        }

        return false;
    }

    getConflictInfo(currentClassId, lessonIndex, classroom, allClasses) {
        if (!classroom || classroom === 'ДИСТАНТ' || classroom === 'ВЕР СТАТ') {
            return [];
        }

        const conflicts = [];

        allClasses.forEach(classObj => {
            if (classObj.id !== currentClassId) {
                const lesson = classObj.lessons[lessonIndex];
                if (lesson && lesson.classrooms && lesson.classrooms.length > 0) {
                    lesson.classrooms.forEach(c => {
                        const otherClassroom = typeof c === 'object' ? c.classroom : c;
                        if (otherClassroom === classroom && lesson.subject && lesson.subject !== '--|--') {
                            conflicts.push({
                                classId: classObj.id,
                                className: classObj.name,
                                subject: lesson.subject,
                                classroom: classroom
                            });
                        }
                    });
                }
            }
        });

        return conflicts;
    }

    checkAndHandleConflicts(classId, lessonIndex, classroom, allClasses, uiManager) {
        if (!classroom || classroom === 'ДИСТАНТ' || classroom === 'ВЕР СТАТ') {
            return;
        }

        const conflicts = this.getConflictInfo(classId, lessonIndex, classroom, allClasses);

        if (conflicts.length > 0) {
            this.pendingSelection = { classId, lessonIndex, classroom };
            uiManager.showCombinedLessonDialog(classroom, lessonIndex, conflicts[0], allClasses);
        }
    }

    updateAllConflicts(allClasses) {
        this.classroomConflicts.clear();
        const occupied = new Map();

        allClasses.forEach(classObj => {
            classObj.lessons.forEach((lesson, index) => {
                if (lesson.classrooms && lesson.classrooms.length > 0 &&
                    lesson.subject && lesson.subject !== '--|--') {

                    lesson.classrooms.forEach(classroomObj => {
                        const classroom = typeof classroomObj === 'object' ? classroomObj.classroom : classroomObj;

                        if (classroom && classroom !== 'ДИСТАНТ' && classroom !== 'ВЕР СТАТ') {
                            const key = `${classroom}_${index}`;

                            if (!occupied.has(key)) {
                                occupied.set(key, []);
                            }

                            occupied.get(key).push({
                                classId: classObj.id,
                                className: classObj.name,
                                subject: lesson.subject,
                                classroom: classroom
                            });
                        }
                    });
                }
            });
        });

        occupied.forEach((classes, key) => {
            if (classes.length > 1) {
                this.classroomConflicts.set(key, classes);
            }
        });
    }

    clearConflicts() {
        this.classroomConflicts.clear();
    }
}