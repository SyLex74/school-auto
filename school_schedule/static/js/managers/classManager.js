// Управление классами и уроками
class ClassManager {
    constructor() {
        this.classes = [];
    }

    addClass(classData = null) {
        const classId = 'class_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        const classObj = {
            id: classId,
            name: classData?.name || '',
            lessons: classData?.lessons || [
                { subject: '', lessonType: '', classrooms: [] },
                { subject: '', lessonType: '', classrooms: [] },
                { subject: '', lessonType: '', classrooms: [] }
            ]
        };

        this.classes.push(classObj);
        return classObj;
    }

    deleteClass(classId) {
        this.classes = this.classes.filter(c => c.id !== classId);
    }

    updateClassName(classId, newName) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj) {
            classObj.name = newName;
        }
    }

    addLessonRow(classId) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj) {
            classObj.lessons.push({
                subject: '',
                lessonType: '',
                classrooms: []
            });
            return true;
        }
        return false;
    }

    addSkipRow(classId) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj) {
            classObj.lessons.push({
                subject: '--|--',
                lessonType: '',
                classrooms: []
            });
            return true;
        }
        return false;
    }

    deleteLesson(classId, lessonIndex) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj && classObj.lessons.length > 1) {
            classObj.lessons.splice(lessonIndex, 1);
            return true;
        }
        return false;
    }

    updateLessonSubject(classId, lessonIndex, subject) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj && classObj.lessons[lessonIndex]) {
            classObj.lessons[lessonIndex].subject = subject;
            if (subject === '--|--') {
                classObj.lessons[lessonIndex].lessonType = '';
                classObj.lessons[lessonIndex].classrooms = [];
            }
            return true;
        }
        return false;
    }

    addClassroomToLesson(classId, lessonIndex, classroom) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj && classObj.lessons[lessonIndex]) {
            const lesson = classObj.lessons[lessonIndex];

            if (!lesson.classrooms) {
                lesson.classrooms = [];
            }

            const existingIndex = lesson.classrooms.findIndex(c =>
                typeof c === 'object' ? c.classroom === classroom : c === classroom
            );

            if (existingIndex !== -1) {
                return false; // Уже существует
            }

            lesson.classrooms.push({
                type: '',
                classroom: classroom
            });

            return true;
        }
        return false;
    }

    removeClassroomFromLesson(classId, lessonIndex, classroom) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj && classObj.lessons[lessonIndex]) {
            const lesson = classObj.lessons[lessonIndex];

            if (lesson.classrooms) {
                const index = lesson.classrooms.findIndex(c =>
                    typeof c === 'object' ? c.classroom === classroom : c === classroom
                );

                if (index !== -1) {
                    lesson.classrooms.splice(index, 1);
                    return true;
                }
            }
        }
        return false;
    }

    updateClassroomType(classId, lessonIndex, classroomIndex, type) {
        const classObj = this.classes.find(c => c.id === classId);
        if (classObj && classObj.lessons[lessonIndex]) {
            const lesson = classObj.lessons[lessonIndex];
            if (lesson.classrooms && lesson.classrooms[classroomIndex]) {
                const classroomObj = lesson.classrooms[classroomIndex];
                if (typeof classroomObj === 'string') {
                    lesson.classrooms[classroomIndex] = {
                        type: type,
                        classroom: classroomObj
                    };
                } else {
                    classroomObj.type = type;
                }
                return true;
            }
        }
        return false;
    }

    getClass(classId) {
        return this.classes.find(c => c.id === classId);
    }

    hasValidData() {
        return this.classes.some(c =>
            c.name.trim() && c.lessons.some(l => l.subject && l.subject !== '--|--')
        );
    }
}