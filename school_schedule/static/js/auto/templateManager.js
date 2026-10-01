// templateManager.js
class TemplateManager {
    constructor() {
        this.storageKey = 'schedule_templates';
        this.templates = this.loadTemplates();
    }

    loadTemplates() {
        const stored = localStorage.getItem(this.storageKey);
        return stored ? JSON.parse(stored) : [];
    }

    saveTemplates() {
        localStorage.setItem(this.storageKey, JSON.stringify(this.templates));
    }

    getTemplates() {
        return this.templates;
    }

    getTemplate(id) {
        return this.templates.find(t => t.id === id);
    }

    addTemplate(template) {
        template.id = Date.now() + '_' + Math.random().toString(36).substr(2, 6);
        this.templates.push(template);
        this.saveTemplates();
        return template;
    }

    updateTemplate(id, updates) {
        const index = this.templates.findIndex(t => t.id === id);
        if (index !== -1) {
            this.templates[index] = { ...this.templates[index], ...updates };
            this.saveTemplates();
            return this.templates[index];
        }
        return null;
    }

    deleteTemplate(id) {
        this.templates = this.templates.filter(t => t.id !== id);
        this.saveTemplates();
    }
}