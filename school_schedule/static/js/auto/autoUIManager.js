// autoUIManager.js
// Полностью исправленная версия с удобным добавлением классов, предметов, кабинетов и часов

class AutoUIManager {
    constructor() {
        this.templateManager = new TemplateManager();
        this.currentDay = null;
        this.currentTemplate = null;
        this.generatedClasses = null;        // для одного дня
        this.generatedWeek = null;           // для всей недели
        this.isAuthenticated = document.getElementById('isAuthenticated')?.value === 'true';
        this.standardSubjects = [...Constants.SUBJECTS];
        this.standardClassrooms = [...Constants.CLASSROOMS];
        this.customSubjects = [];
        this.customClassrooms = [];
        this.updateAllLists();
        this.loadCustomItems();
        this.currentStep = 1;
        // Расширенная структура данных шаблона
        this.templateData = {
            name: '',
            classes: [],               // [{ name: "5А" }]
            subjects: [],             // [{ name: "Математика", preferredClassrooms: [] }]
            classrooms: [],           // [{ name: "101" }]
            classSubjectHours: []     // [{ className, subjectName, hoursPerWeek, preferredDays }]
        };
        this.daysOfWeek = [
            { key: 'monday', label: 'Понедельник' },
            { key: 'tuesday', label: 'Вторник' },
            { key: 'wednesday', label: 'Среда' },
            { key: 'thursday', label: 'Четверг' },
            { key: 'friday', label: 'Пятница' },
            { key: 'saturday', label: 'Суббота' }
        ];
    }

    updateAllLists() {
        this.allSubjects = [...this.standardSubjects, ...this.customSubjects];
        this.allClassrooms = [...this.standardClassrooms, ...this.customClassrooms];
    }

    loadCustomItems() {
        const storedSubjects = localStorage.getItem('custom_subjects');
        const storedClassrooms = localStorage.getItem('custom_classrooms');
        if (storedSubjects) this.customSubjects = JSON.parse(storedSubjects);
        if (storedClassrooms) this.customClassrooms = JSON.parse(storedClassrooms);
        this.updateAllLists();
    }

    saveCustomItems() {
        localStorage.setItem('custom_subjects', JSON.stringify(this.customSubjects));
        localStorage.setItem('custom_classrooms', JSON.stringify(this.customClassrooms));
        this.updateAllLists();
    }

    init() {
        this.setupDayButtons();
        this.setupCreateTemplateButton();
        this.setupRegenerateButton();
        this.setupSaveButton();
        this.loadTemplatesList();
        const genWeekBtn = document.getElementById('generateWeekBtn');
        if (genWeekBtn) genWeekBtn.addEventListener('click', () => this.generateFullWeek());
    }

    setupDayButtons() {
        document.querySelectorAll('.auto-day-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.currentDay = e.target.dataset.day;
                document.querySelectorAll('.auto-day-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                document.getElementById('templateSelection').style.display = 'block';
                this.loadTemplatesList();
                if (this.generatedWeek && this.generatedWeek[this.currentDay]) {
                    this.generatedClasses = this.generatedWeek[this.currentDay];
                    this.displaySchedule();
                }
            });
        });
    }

    async loadTemplatesList() {
        const templates = await this.loadTemplatesFromServer();
        const container = document.getElementById('templateList');
        container.innerHTML = '';
        if (!templates || templates.length === 0) {
            container.innerHTML = '<p class="auto-empty-message">Нет шаблонов. Создайте новый.</p>';
            return;
        }
        templates.forEach(tpl => {
            const div = document.createElement('div');
            div.className = 'template-item';
            div.textContent = tpl.name;
            div.dataset.id = tpl.id;
            div.addEventListener('click', () => {
                document.querySelectorAll('.template-item').forEach(i => i.classList.remove('active'));
                div.classList.add('active');
                this.currentTemplate = tpl;
                this.generateSchedule();
            });
            container.appendChild(div);
        });
    }

    async loadTemplatesFromServer() {
        if (!this.isAuthenticated) return this.templateManager.getTemplates();
        try {
            const response = await fetch('/api/templates/');
            const data = await response.json();
            return data.templates || [];
        } catch(e) {
            return this.templateManager.getTemplates();
        }
    }

    generateSchedule() {
        if (!this.currentDay || !this.currentTemplate) return;
        const generator = new ScheduleGenerator(this.currentTemplate, this.currentDay, Constants.DAY_NAMES);
        this.generatedClasses = generator.generate();
        this.displaySchedule();
    }

    generateFullWeek() {
        if (!this.currentTemplate) {
            alert("Сначала выберите шаблон");
            return;
        }
        const generator = new ScheduleGenerator(this.currentTemplate, 'monday', Constants.DAY_NAMES);
        this.generatedWeek = generator.generateFullWeek();
        if (this.currentDay && this.generatedWeek[this.currentDay]) {
            this.generatedClasses = this.generatedWeek[this.currentDay];
            this.displaySchedule();
        } else if (this.currentDay) {
            alert("Ошибка генерации недели");
        }
    }

    displaySchedule() {
        const scheduleArea = document.getElementById('scheduleArea');
        const container = document.getElementById('classesContainer');
        const title = document.getElementById('selectedDayTitle');
        title.textContent = `Сгенерированное расписание на ${Constants.DAY_NAMES[this.currentDay]}`;
        container.innerHTML = '';
        for (let classObj of this.generatedClasses) {
            this.renderClassTable(classObj, container);
        }
        scheduleArea.classList.remove('hidden');
        const saveBtn = document.getElementById('saveScheduleBtn');
        if (saveBtn && this.isAuthenticated) saveBtn.style.display = 'inline-block';
    }

    renderClassTable(classObj, container) {
        const wrapper = document.createElement('div');
        wrapper.className = 'class-table-wrapper';
        wrapper.dataset.classId = classObj.id;
        wrapper.innerHTML = `
            <div class="class-header">
                <span class="class-name-title">${this.escapeHtml(classObj.name)}</span>
            </div>
            <table class="schedule-table">
                <thead><tr><th>№</th><th>Предмет</th><th>Кабинеты</th></tr></thead>
                <tbody>
                    ${classObj.lessons.map((lesson, idx) => `
                        <tr>
                            <td>${idx+1}</td>
                            <td>${this.escapeHtml(lesson.subject || '—')}</td>
                            <td>${lesson.classrooms.map(c => this.escapeHtml(c.classroom)).join(', ') || '—'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        container.appendChild(wrapper);
    }

    escapeHtml(str) {
        if (!str) return '';
        return str.replace(/[&<>]/g, function(m) {
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        });
    }

    setupRegenerateButton() {
        document.getElementById('regenerateBtn')?.addEventListener('click', () => {
            if (this.currentTemplate) this.generateSchedule();
        });
    }

    setupSaveButton() {
        document.getElementById('saveScheduleBtn')?.addEventListener('click', async () => {
            if (!this.currentDay || !this.generatedClasses) return;
            let payload;
            if (this.generatedWeek) {
                payload = { week: this.generatedWeek };
            } else {
                payload = { day: this.currentDay, schedule: this.generatedClasses };
            }
            try {
                const response = await fetch('/api/save/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.getElementById('csrfToken')?.value || ''
                    },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (result.status === 'ok') {
                    alert('Расписание сохранено в профиль!');
                    window.location.href = '/profile/';
                } else {
                    alert('Ошибка сохранения');
                }
            } catch(err) { console.error(err); alert('Ошибка сети'); }
        });
    }

    setupCreateTemplateButton() {
        document.getElementById('createNewTemplateBtn')?.addEventListener('click', () => {
            this.currentStep = 1;
            this.templateData = {
                name: '',
                classes: [],
                subjects: [],
                classrooms: [],
                classSubjectHours: []
            };
            this.openWizard();
        });
    }

    openWizard() {
        const modal = document.getElementById('templateModal');
        const modalBody = document.getElementById('templateModalBody');
        const modalTitle = document.getElementById('modalTitle');
        modalTitle.textContent = 'Создание шаблона - Шаг 1: Классы';
        modalBody.innerHTML = this.getStep1HTML();
        modal.classList.remove('hidden');
        this.attachWizardEvents();
    }

    // ==================== ШАГ 1: КЛАССЫ (исправлен) ====================
    getStep1HTML() {
        return `
            <div class="wizard-step">
                <h3>Шаг 1: Классы</h3>
                <div id="wizardClassesList" class="dynamic-list"></div>
                <div style="margin-top: 10px; display: flex; gap: 8px;">
                    <input type="text" id="newClassNameInput" placeholder="Название класса (например, 5А)" style="flex:1;">
                    <button type="button" id="wizardAddClassBtn" class="add-btn">+ Добавить класс</button>
                </div>
                <div style="margin-top: 15px;">
                    <label>Название шаблона: <input type="text" id="templateNameInput" value="${this.escapeHtml(this.templateData.name)}" placeholder="Мой шаблон"></label>
                </div>
                <div class="wizard-buttons">
                    <button id="wizardNextBtn" class="auto-btn-primary">Далее</button>
                    <button class="modal-close auto-btn-secondary">Отмена</button>
                </div>
            </div>
        `;
    }

    addWizardClass() {
        const input = document.getElementById('newClassNameInput');
        const val = input.value.trim();
        if (val && !this.templateData.classes.some(c => c.name === val)) {
            this.templateData.classes.push({ name: val });
            this.renderWizardClasses();
            input.value = '';
        } else if (val) {
            alert('Такой класс уже есть');
        } else {
            alert('Введите название класса');
        }
    }

    renderWizardClasses() {
        const container = document.getElementById('wizardClassesList');
        if (!container) return;
        container.innerHTML = '';
        this.templateData.classes.forEach((cls, idx) => {
            const div = document.createElement('div');
            div.className = 'dynamic-row';
            const span = document.createElement('span');
            span.textContent = cls.name;
            span.style.flex = '1';
            const delBtn = document.createElement('button');
            delBtn.textContent = '✖';
            delBtn.className = 'remove-row-btn';
            delBtn.onclick = () => {
                this.templateData.classes.splice(idx, 1);
                this.renderWizardClasses();
            };
            div.appendChild(span);
            div.appendChild(delBtn);
            container.appendChild(div);
        });
    }

    // ==================== ШАГ 2: ПРЕДМЕТЫ И КАБИНЕТЫ ====================
    getStep2HTML() {
        return `
            <div class="wizard-step">
                <h3>Шаг 2: Предметы и их кабинеты</h3>
                <div id="wizardSubjectsContainer" style="max-height: 400px; overflow-y: auto;"></div>
                <div class="custom-add" style="margin-top:10px;">
                    <input type="text" id="newSubjectName" placeholder="Новый предмет" style="padding:6px; width:200px;">
                    <button type="button" id="addCustomSubjectWizard" class="add-btn">Добавить свой</button>
                </div>
                <div class="wizard-buttons" style="margin-top:20px;">
                    <button id="wizardPrevBtn" class="auto-btn-secondary">Назад</button>
                    <button id="wizardNextBtn" class="auto-btn-primary">Далее</button>
                    <button class="modal-close auto-btn-secondary">Отмена</button>
                </div>
            </div>
        `;
    }

    renderWizardSubjectsWithClassrooms() {
        const container = document.getElementById('wizardSubjectsContainer');
        if (!container) return;
        container.innerHTML = '';
        this.allSubjects.forEach(sub => {
            const existing = this.templateData.subjects.find(s => s.name === sub);
            const selected = !!existing;
            const preferredClassrooms = existing ? existing.preferredClassrooms || [] : [];
            
            const div = document.createElement('div');
            div.className = 'subject-item';
            div.style.marginBottom = '12px';
            div.style.padding = '8px';
            div.style.border = '1px solid #ddd';
            div.style.borderRadius = '4px';
            
            const header = document.createElement('div');
            header.style.display = 'flex';
            header.style.alignItems = 'center';
            header.style.marginBottom = '5px';
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.checked = selected;
            chk.style.marginRight = '8px';
            chk.addEventListener('change', (e) => {
                if (e.target.checked) {
                    if (!this.templateData.subjects.find(s => s.name === sub)) {
                        this.templateData.subjects.push({ name: sub, preferredClassrooms: [] });
                    }
                } else {
                    const idx = this.templateData.subjects.findIndex(s => s.name === sub);
                    if (idx !== -1) this.templateData.subjects.splice(idx, 1);
                }
                this.renderWizardSubjectsWithClassrooms();
            });
            const label = document.createElement('span');
            label.textContent = sub;
            label.style.fontWeight = 'bold';
            header.appendChild(chk);
            header.appendChild(label);
            
            const roomsDiv = document.createElement('div');
            roomsDiv.style.marginLeft = '24px';
            roomsDiv.style.fontSize = '0.9em';
            if (selected) {
                roomsDiv.innerHTML = '<small>Предпочтительные кабинеты:</small><br>';
                this.allClassrooms.forEach(room => {
                    const roomChk = document.createElement('input');
                    roomChk.type = 'checkbox';
                    roomChk.value = room;
                    roomChk.checked = preferredClassrooms.includes(room);
                    roomChk.style.marginRight = '4px';
                    roomChk.addEventListener('change', () => {
                        const subj = this.templateData.subjects.find(s => s.name === sub);
                        if (subj) {
                            if (roomChk.checked) {
                                if (!subj.preferredClassrooms.includes(room)) subj.preferredClassrooms.push(room);
                            } else {
                                const idxRoom = subj.preferredClassrooms.indexOf(room);
                                if (idxRoom !== -1) subj.preferredClassrooms.splice(idxRoom, 1);
                            }
                        }
                    });
                    const roomLabel = document.createTextNode(room);
                    roomsDiv.appendChild(roomChk);
                    roomsDiv.appendChild(roomLabel);
                    roomsDiv.appendChild(document.createElement('br'));
                });
            }
            div.appendChild(header);
            if (selected) div.appendChild(roomsDiv);
            container.appendChild(div);
        });
    }

    addWizardSubject() {
        const input = document.getElementById('newSubjectName');
        const name = input.value.trim();
        if (name && !this.allSubjects.includes(name)) {
            this.customSubjects.push(name);
            this.saveCustomItems();
            this.renderWizardSubjectsWithClassrooms();
            input.value = '';
        } else if (name) {
            alert('Такой предмет уже есть');
        } else {
            alert('Введите название предмета');
        }
    }

    // ==================== ШАГ 3: КАБИНЕТЫ ====================
    getStep3HTML() {
        return `
            <div class="wizard-step">
                <h3>Шаг 3: Кабинеты</h3>
                <div id="wizardClassroomsList" class="selects-list" style="max-height:300px; overflow-y:auto;"></div>
                <div class="custom-add" style="margin-top:10px;">
                    <input type="text" id="newClassroomName" placeholder="Новый кабинет" style="padding:6px; width:200px;">
                    <button type="button" id="addCustomClassroomWizard" class="add-btn">Добавить свой</button>
                </div>
                <div class="wizard-buttons" style="margin-top:20px;">
                    <button id="wizardPrevBtn" class="auto-btn-secondary">Назад</button>
                    <button id="wizardNextBtn" class="auto-btn-primary">Далее</button>
                    <button class="modal-close auto-btn-secondary">Отмена</button>
                </div>
            </div>
        `;
    }

    renderWizardClassrooms() {
        const container = document.getElementById('wizardClassroomsList');
        if (!container) return;
        container.innerHTML = '';
        this.allClassrooms.forEach(room => {
            const isSelected = this.templateData.classrooms.some(c => c.name === room);
            const label = document.createElement('label');
            label.style.display = 'block';
            label.style.marginBottom = '6px';
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.value = room;
            chk.checked = isSelected;
            chk.addEventListener('change', (e) => {
                if (e.target.checked) {
                    if (!this.templateData.classrooms.some(c => c.name === room)) {
                        this.templateData.classrooms.push({ name: room });
                    }
                } else {
                    const idx = this.templateData.classrooms.findIndex(c => c.name === room);
                    if (idx !== -1) this.templateData.classrooms.splice(idx, 1);
                }
            });
            label.appendChild(chk);
            label.appendChild(document.createTextNode(' ' + room));
            container.appendChild(label);
        });
    }

    addWizardClassroom() {
        const input = document.getElementById('newClassroomName');
        const name = input.value.trim();
        if (name && !this.allClassrooms.includes(name)) {
            this.customClassrooms.push(name);
            this.saveCustomItems();
            this.renderWizardClassrooms();
            input.value = '';
        } else if (name) {
            alert('Такой кабинет уже есть');
        } else {
            alert('Введите название кабинета');
        }
    }

    // ==================== ШАГ 4: ЧАСЫ И ДНИ ====================
    getStep4HTML() {
        const classNames = this.templateData.classes.map(c => c.name);
        const subjects = this.templateData.subjects;
        return `
            <div class="wizard-step">
                <h3>Шаг 4: Часы в неделю и предпочтительные дни</h3>
                <div id="hoursTableContainer" style="overflow-x: auto;">
                    <table id="wizardHoursTable" class="hours-table">
                        <thead>
                            <tr>
                                <th>Класс / Предмет</th>
                                ${subjects.map(s => `<th>${this.escapeHtml(s.name)}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody>
                            ${classNames.map(cls => `
                                <tr>
                                    <td><strong>${this.escapeHtml(cls)}</strong></td>
                                    ${subjects.map(sub => {
                                        let hours = 0;
                                        let daysPref = [];
                                        const existing = this.templateData.classSubjectHours.find(h => h.className === cls && h.subjectName === sub.name);
                                        if (existing) {
                                            hours = existing.hoursPerWeek;
                                            daysPref = existing.preferredDays || [];
                                        }
                                        const daysStr = daysPref.join(',');
                                        return `<td style="text-align:center;">
                                            <input type="number" min="0" max="12" step="1" value="${hours}" 
                                                   data-class="${cls}" data-subject="${sub.name}" 
                                                   class="hours-input" style="width:70px;">
                                            <button type="button" class="pref-days-btn" 
                                                    data-class="${cls}" data-subject="${sub.name}"
                                                    data-days="${daysStr}">📅</button>
                                        </td>`;
                                    }).join('')}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="wizard-buttons" style="margin-top:20px;">
                    <button id="wizardPrevBtn" class="auto-btn-secondary">Назад</button>
                    <button id="wizardSaveBtn" class="auto-btn-primary">Сохранить шаблон</button>
                    <button class="modal-close auto-btn-secondary">Отмена</button>
                </div>
            </div>
        `;
    }

    showDaysPicker(className, subjectName, currentDays, triggerButton) {
        const daysList = this.daysOfWeek.map(d => d.key);
        const modal = document.createElement('div');
        modal.className = 'days-picker-modal';
        modal.style.position = 'fixed';
        modal.style.top = '50%';
        modal.style.left = '50%';
        modal.style.transform = 'translate(-50%, -50%)';
        modal.style.backgroundColor = 'white';
        modal.style.padding = '20px';
        modal.style.border = '1px solid #ccc';
        modal.style.zIndex = '2000';
        modal.style.boxShadow = '0 0 10px rgba(0,0,0,0.3)';
        
        const title = document.createElement('h4');
        title.textContent = `Выберите дни для ${className} – ${subjectName}`;
        modal.appendChild(title);
        
        const checkboxes = {};
        daysList.forEach(day => {
            const label = document.createElement('label');
            label.style.display = 'block';
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.value = day;
            chk.checked = currentDays.includes(day);
            checkboxes[day] = chk;
            label.appendChild(chk);
            label.appendChild(document.createTextNode(this.daysOfWeek.find(d => d.key === day).label));
            modal.appendChild(label);
        });
        
        const btnOk = document.createElement('button');
        btnOk.textContent = 'OK';
        btnOk.style.marginTop = '10px';
        btnOk.onclick = () => {
            const selected = daysList.filter(day => checkboxes[day].checked);
            let entry = this.templateData.classSubjectHours.find(h => h.className === className && h.subjectName === subjectName);
            if (entry) {
                entry.preferredDays = selected;
            } else {
                this.templateData.classSubjectHours.push({
                    className, subjectName, hoursPerWeek: 0, preferredDays: selected
                });
            }
            if (triggerButton) triggerButton.dataset.days = selected.join(',');
            document.body.removeChild(modal);
            document.body.removeChild(overlay);
        };
        modal.appendChild(btnOk);
        
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.top = 0;
        overlay.style.left = 0;
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
        overlay.style.zIndex = '1999';
        overlay.onclick = () => {
            document.body.removeChild(overlay);
            if (document.body.contains(modal)) document.body.removeChild(modal);
        };
        document.body.appendChild(overlay);
        document.body.appendChild(modal);
    }

    // ==================== ВАЛИДАЦИЯ ====================
    validateStep1() {
        if (this.templateData.classes.length === 0) {
            alert('Добавьте хотя бы один класс');
            return false;
        }
        if (!this.templateData.name.trim()) {
            alert('Введите название шаблона');
            return false;
        }
        return true;
    }

    validateStep2() {
        if (this.templateData.subjects.length === 0) {
            alert('Выберите хотя бы один предмет');
            return false;
        }
        return true;
    }

    validateStep3() {
        if (this.templateData.classrooms.length === 0) {
            alert('Выберите хотя бы один кабинет');
            return false;
        }
        return true;
    }

    // ==================== ОБНОВЛЕНИЕ СОДЕРЖИМОГО МАСТЕРА ====================
    updateWizardContent() {
        const modalBody = document.getElementById('templateModalBody');
        const modalTitle = document.getElementById('modalTitle');
        let html = '';
        if (this.currentStep === 1) {
            modalTitle.textContent = 'Создание шаблона - Шаг 1: Классы';
            html = this.getStep1HTML();
        } else if (this.currentStep === 2) {
            modalTitle.textContent = 'Создание шаблона - Шаг 2: Предметы и кабинеты';
            html = this.getStep2HTML();
        } else if (this.currentStep === 3) {
            modalTitle.textContent = 'Создание шаблона - Шаг 3: Кабинеты';
            html = this.getStep3HTML();
        } else if (this.currentStep === 4) {
            modalTitle.textContent = 'Создание шаблона - Шаг 4: Часы и дни';
            html = this.getStep4HTML();
        }
        modalBody.innerHTML = html;
        this.attachWizardEvents();
    }

    attachWizardEvents() {
        const modal = document.getElementById('templateModal');
        const nextBtn = document.getElementById('wizardNextBtn');
        const prevBtn = document.getElementById('wizardPrevBtn');

        if (this.currentStep === 1) {
            const addBtn = document.getElementById('wizardAddClassBtn');
            if (addBtn) addBtn.onclick = () => this.addWizardClass();
            this.renderWizardClasses();
            const nameInput = document.getElementById('templateNameInput');
            if (nameInput) nameInput.addEventListener('input', (e) => { this.templateData.name = e.target.value; });
        }
        else if (this.currentStep === 2) {
            this.renderWizardSubjectsWithClassrooms();
            const addSubjectBtn = document.getElementById('addCustomSubjectWizard');
            if (addSubjectBtn) addSubjectBtn.onclick = () => this.addWizardSubject();
        }
        else if (this.currentStep === 3) {
            this.renderWizardClassrooms();
            const addClassroomBtn = document.getElementById('addCustomClassroomWizard');
            if (addClassroomBtn) addClassroomBtn.onclick = () => this.addWizardClassroom();
        }
        else if (this.currentStep === 4) {
            const saveBtn = document.getElementById('wizardSaveBtn');
            if (saveBtn) saveBtn.onclick = () => this.saveWizardTemplate();
            document.querySelectorAll('.pref-days-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const className = btn.dataset.class;
                    const subjectName = btn.dataset.subject;
                    const currentDaysStr = btn.dataset.days;
                    const currentDays = currentDaysStr ? currentDaysStr.split(',') : [];
                    this.showDaysPicker(className, subjectName, currentDays, btn);
                });
            });
            document.querySelectorAll('.hours-input').forEach(inp => {
                inp.addEventListener('change', () => {
                    const className = inp.dataset.class;
                    const subjectName = inp.dataset.subject;
                    const hours = parseInt(inp.value, 10);
                    const existingIndex = this.templateData.classSubjectHours.findIndex(h => h.className === className && h.subjectName === subjectName);
                    if (hours > 0) {
                        if (existingIndex !== -1) {
                            this.templateData.classSubjectHours[existingIndex].hoursPerWeek = hours;
                        } else {
                            this.templateData.classSubjectHours.push({ className, subjectName, hoursPerWeek: hours, preferredDays: [] });
                        }
                    } else {
                        if (existingIndex !== -1) this.templateData.classSubjectHours.splice(existingIndex, 1);
                    }
                });
            });
        }

        if (nextBtn) {
            nextBtn.onclick = () => {
                if (this.currentStep === 1 && this.validateStep1()) {
                    this.currentStep = 2;
                    this.updateWizardContent();
                } else if (this.currentStep === 2 && this.validateStep2()) {
                    this.currentStep = 3;
                    this.updateWizardContent();
                } else if (this.currentStep === 3 && this.validateStep3()) {
                    this.currentStep = 4;
                    this.updateWizardContent();
                }
            };
        }
        if (prevBtn) {
            prevBtn.onclick = () => {
                if (this.currentStep > 1) {
                    this.currentStep--;
                    this.updateWizardContent();
                }
            };
        }
        modal.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => modal.classList.add('hidden'));
        });
    }

    saveWizardTemplate() {
        const hoursInputs = document.querySelectorAll('.hours-input');
        hoursInputs.forEach(inp => {
            const className = inp.dataset.class;
            const subjectName = inp.dataset.subject;
            const hours = parseInt(inp.value, 10);
            const existingIndex = this.templateData.classSubjectHours.findIndex(h => h.className === className && h.subjectName === subjectName);
            if (hours > 0) {
                if (existingIndex !== -1) {
                    this.templateData.classSubjectHours[existingIndex].hoursPerWeek = hours;
                } else {
                    this.templateData.classSubjectHours.push({ className, subjectName, hoursPerWeek: hours, preferredDays: [] });
                }
            } else {
                if (existingIndex !== -1) this.templateData.classSubjectHours.splice(existingIndex, 1);
            }
        });
        
        const template = {
            id: Date.now().toString(),
            name: this.templateData.name,
            classes: this.templateData.classes,
            subjects: this.templateData.subjects,
            classrooms: this.templateData.classrooms,
            classSubjectHours: this.templateData.classSubjectHours
        };
        
        if (this.isAuthenticated) this.saveTemplateToServer(template);
        this.templateManager.addTemplate(template);
        document.getElementById('templateModal').classList.add('hidden');
        this.loadTemplatesList();
        alert('Шаблон сохранён!');
    }

    async saveTemplateToServer(template) {
        if (!this.isAuthenticated) return;
        try {
            await fetch('/api/templates/save/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.getElementById('csrfToken')?.value
                },
                body: JSON.stringify(template)
            });
        } catch(e) { console.error('Ошибка сохранения шаблона на сервер', e); }
    }
}