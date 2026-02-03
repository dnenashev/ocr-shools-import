// State
let token = localStorage.getItem('admin_token');
let currentPage = 0;
let pageSize = 20;
let totalStudents = 0;
let currentFilter = '';
let searchQuery = '';
let deleteStudentId = null;
let editStudentId = null;
/** Выбранные заявки для массовой отправки в AMO (id → true) */
let selectedStudentIds = new Set();

// DOM Elements
const loginPage = document.getElementById('loginPage');
const adminPanel = document.getElementById('adminPanel');
const loginForm = document.getElementById('loginForm');
const studentsTable = document.getElementById('studentsTable');
const searchInput = document.getElementById('searchInput');
const filterSelect = document.getElementById('filterSelect');
const toastContainer = document.getElementById('toastContainer');

// Page from URL (#page/1, #page/16 ...)
function getPageFromUrl() {
    const m = (window.location.hash || '').match(/^#?page\/(\d+)$/i);
    if (!m) return 0;
    const num = parseInt(m[1], 10);
    return num > 0 ? num - 1 : 0; // 1-based in URL -> 0-based
}

function setPageInUrl(pageIndex) {
    const page = Math.max(0, pageIndex);
    const newHash = '#page/' + (page + 1);
    if (window.location.hash !== newHash) {
        window.location.hash = newHash;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (token) {
        checkAuth();
    } else {
        showLogin();
    }

    // Event listeners
    loginForm.addEventListener('submit', handleLogin);
    searchInput.addEventListener('input', debounce(handleSearch, 300));
    filterSelect.addEventListener('change', handleFilter);

    // При смене hash вручную — перейти на указанную страницу
    window.addEventListener('hashchange', () => {
        if (!adminPanel.classList.contains('active')) return;
        const pageFromUrl = getPageFromUrl();
        if (pageFromUrl !== currentPage) {
            currentPage = pageFromUrl;
            loadStudents();
        }
    });
});

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 4000);
}

// Auth functions
async function checkAuth() {
    try {
        const response = await fetch('/api/admin/stats', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            showAdmin();
            currentPage = getPageFromUrl();
            loadStats();
            loadStudents();
        } else {
            localStorage.removeItem('admin_token');
            token = null;
            showLogin();
        }
    } catch (error) {
        showLogin();
    }
}

function showLogin() {
    loginPage.style.display = 'flex';
    adminPanel.classList.remove('active');
}

function showAdmin() {
    loginPage.style.display = 'none';
    adminPanel.classList.add('active');
}

async function handleLogin(e) {
    e.preventDefault();
    const password = document.getElementById('password').value;
    
    try {
        const response = await fetch('/api/admin/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            token = data.token;
            localStorage.setItem('admin_token', token);
            showToast('Вход выполнен успешно', 'success');
            showAdmin();
            loadStats();
            loadStudents();
        } else {
            showToast(data.detail || 'Ошибка авторизации', 'error');
        }
    } catch (error) {
        showToast('Ошибка подключения к серверу', 'error');
    }
}

async function logout() {
    try {
        await fetch('/api/admin/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    } catch (error) {}
    
    localStorage.removeItem('admin_token');
    token = null;
    showLogin();
    showToast('Выход выполнен', 'info');
}

// Data functions
async function loadStats() {
    try {
        const response = await fetch('/api/admin/stats', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            document.getElementById('totalCount').textContent = data.total;
            document.getElementById('sentCount').textContent = data.sent_to_amo;
            document.getElementById('pendingCount').textContent = data.not_sent;
            
            // Детализация по контактам
            updateStatsDetail(data.sent_to_amo, data.sent_with_student_contact, data.sent_with_parent_contact);
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function updateStatsDetail(sentCount, studentContactCount, parentContactCount) {
    const sentDetail = document.getElementById('sentDetail');
    if (sentCount > 0) {
        const studentCount = studentContactCount || 0;
        const parentCount = parentContactCount || 0;
        sentDetail.textContent = `С контактом ребенка: ${studentCount}, с контактом родителя: ${parentCount}`;
    } else {
        sentDetail.textContent = '';
    }
}

function updateStatsWithContactData(studentContactCount, parentContactCount) {
    // Обновляем только детализацию контактов, общие данные загружаем отдельно
    const sentCount = parseInt(document.getElementById('sentCount').textContent) || 0;
    updateStatsDetail(sentCount, studentContactCount, parentContactCount);
    
    // Также обновляем общую статистику
    loadStats();
}

async function loadStudents() {
    studentsTable.innerHTML = `
        <tr>
            <td colspan="9">
                <div class="loading">
                    <div class="spinner"></div>
                </div>
            </td>
        </tr>
    `;
    
    try {
        let url = `/api/admin/students?skip=${currentPage * pageSize}&limit=${pageSize}`;
        
        if (currentFilter !== '') {
            url += `&sent_to_amo=${currentFilter}`;
        }
        
        if (searchQuery) {
            url += `&search=${encodeURIComponent(searchQuery)}`;
        }
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            totalStudents = data.total;
            const totalPages = Math.ceil(totalStudents / pageSize);
            if (totalPages > 0 && currentPage >= totalPages) {
                currentPage = totalPages - 1;
                setPageInUrl(currentPage);
            }
            renderStudents(data.students);
            updatePagination();
        } else if (response.status === 401) {
            logout();
        }
    } catch (error) {
        console.error('Error loading students:', error);
        studentsTable.innerHTML = `
            <tr>
                <td colspan="9">
                    <div class="empty-state">
                        <p>Ошибка загрузки данных</p>
                    </div>
                </td>
            </tr>
        `;
    }
}

function renderStudents(students) {
    if (students.length === 0) {
        studentsTable.innerHTML = `
            <tr>
                <td colspan="9">
                    <div class="empty-state">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                        </svg>
                        <p>Нет заявок</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    studentsTable.innerHTML = students.map(student => {
        // Формируем строку с оценками и отзывом
        let feedbackInfo = '';
        if (student.masterclass_rating || student.speaker_rating || student.feedback) {
            feedbackInfo = '<div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">';
            if (student.masterclass_rating) {
                feedbackInfo += `⭐ МК: ${student.masterclass_rating}/10 `;
            }
            if (student.speaker_rating) {
                feedbackInfo += `👤 Спикер: ${student.speaker_rating}/10`;
            }
            if (student.feedback) {
                const shortFeedback = student.feedback.length > 50 
                    ? student.feedback.substring(0, 50) + '...' 
                    : student.feedback;
                feedbackInfo += `<br>💬 ${escapeHtml(shortFeedback)}`;
            }
            feedbackInfo += '</div>';
        }
        
        const isChecked = selectedStudentIds.has(student._id);
        return `
        <tr class="student-row" data-student-id="${escapeHtml(student._id)}" onclick="openEditModal(event)">
            <td class="td-checkbox" onclick="event.stopPropagation()">
                <input type="checkbox" class="row-checkbox" data-student-id="${escapeHtml(student._id)}" ${isChecked ? 'checked' : ''} onchange="toggleSelectStudent(this)">
            </td>
            <td><span style="font-size: 12px; color: var(--accent-primary);">${escapeHtml(student.application_type || '-')}</span></td>
            <td><strong>${escapeHtml(student.fio || '-')}</strong>${feedbackInfo}</td>
            <td>${escapeHtml(student.school || '-')}</td>
            <td>${escapeHtml(student.class || '-')}</td>
            <td>${escapeHtml(student.phone || '-')}</td>
            <td>${formatDate(student.created_at)}</td>
            <td>
                <span class="status-badge ${student.sent_to_amo ? 'sent' : 'pending'}">
                    ${student.sent_to_amo ? 'Отправлено' : 'Ожидает'}
                </span>
            </td>
            <td onclick="event.stopPropagation()">
                <div class="action-buttons">
                    ${!student.sent_to_amo ? `
                        <button class="btn btn-success btn-small" onclick="sendToAmo('${student._id}')" title="Отправить в AMO">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
                            </svg>
                        </button>
                    ` : ''}
                    <button class="btn btn-info btn-small" onclick="sendToAmo('${student._id}')" title="Отправить еще раз в AMO">
                        <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="margin-right: 4px;">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                        </svg>
                        <span>Еще раз</span>
                    </button>
                    ${student.amo_lead_url ? `
                    <a href="${escapeHtml(student.amo_lead_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-small" title="Открыть сделку в AMO">
                        <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="margin-right: 4px;">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
                        </svg>
                        <span>В AMO</span>
                    </a>
                    ` : ''}
                    <button class="btn btn-outline btn-small" onclick="confirmDelete('${student._id}')" title="Удалить">
                        <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                        </svg>
                    </button>
                </div>
            </td>
        </tr>
    `;
    }).join('');

    const selectAllEl = document.getElementById('selectAllCheckbox');
    if (selectAllEl) {
        selectAllEl.onchange = handleSelectAll;
        updateSelectAllState();
    }
}

function toggleSelectStudent(checkboxEl) {
    const id = checkboxEl.getAttribute('data-student-id');
    if (!id) return;
    if (checkboxEl.checked) {
        selectedStudentIds.add(id);
    } else {
        selectedStudentIds.delete(id);
    }
    updateSelectAllState();
}

function handleSelectAll() {
    const selectAll = document.getElementById('selectAllCheckbox');
    if (!selectAll) return;
    const checkboxes = document.querySelectorAll('.row-checkbox');
    const checked = selectAll.checked;
    checkboxes.forEach(cb => {
        cb.checked = checked;
        const id = cb.getAttribute('data-student-id');
        if (id) {
            if (checked) selectedStudentIds.add(id);
            else selectedStudentIds.delete(id);
        }
    });
    updateSelectAllState();
}

function updateSelectAllState() {
    const selectAll = document.getElementById('selectAllCheckbox');
    if (!selectAll) return;
    const checkboxes = document.querySelectorAll('.row-checkbox');
    const n = checkboxes.length;
    const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
    selectAll.checked = n > 0 && checkedCount === n;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < n;
}

async function sendSelectedToAmo() {
    const ids = Array.from(selectedStudentIds);
    if (ids.length === 0) {
        showToast('Выберите заявки галочками', 'error');
        return;
    }
    try {
        showToast(`Отправка ${ids.length} заявок в AMO...`, 'info');
        const response = await fetch('/api/admin/send-to-amo', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ student_ids: ids })
        });
        const data = await response.json();
        if (response.ok) {
            const successCount = data.results?.success?.length || 0;
            const failedCount = data.results?.failed?.length || 0;
            selectedStudentIds.clear();
            updateSelectAllState();
            loadStats();
            loadStudents();
            if (failedCount > 0) {
                showToast(`Отправлено ${successCount}, ошибок: ${failedCount}`, failedCount === ids.length ? 'error' : 'info');
            } else {
                showToast(`Отправлено заявок: ${successCount}`, 'success');
            }
        } else {
            showToast(data.detail || 'Ошибка отправки', 'error');
        }
    } catch (err) {
        showToast('Ошибка подключения', 'error');
    }
}

function updatePagination() {
    const totalPages = Math.ceil(totalStudents / pageSize);
    const pageInfo = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPage');
    const nextBtn = document.getElementById('nextPage');
    
    pageInfo.textContent = `Страница ${currentPage + 1} из ${totalPages || 1}`;
    prevBtn.disabled = currentPage === 0;
    nextBtn.disabled = currentPage >= totalPages - 1;
}

function changePage(delta) {
    currentPage += delta;
    setPageInUrl(currentPage);
    loadStudents();
}

// Search and Filter
function handleSearch() {
    searchQuery = searchInput.value.trim();
    currentPage = 0;
    setPageInUrl(0);
    loadStudents();
}

function handleFilter() {
    currentFilter = filterSelect.value;
    currentPage = 0;
    setPageInUrl(0);
    loadStudents();
}

// AMO CRM functions
async function sendToAmo(studentId) {
    try {
        showToast('Отправка заявки в AMO...', 'info');
        const response = await fetch('/api/admin/send-to-amo', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ student_ids: [studentId] })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const successCount = data.results?.success?.length || 0;
            const failedCount = data.results?.failed?.length || 0;
            
            if (successCount > 0) {
                showToast('Заявка отправлена в AMO', 'success');
            } else if (failedCount > 0) {
                showToast('Не удалось отправить заявку', 'error');
            } else {
                showToast('Заявка отправлена в AMO', 'success');
            }
            loadStats();
            loadStudents();
        } else {
            showToast(data.detail || 'Ошибка отправки', 'error');
        }
    } catch (error) {
        showToast('Ошибка подключения', 'error');
    }
}

async function sendAllToAmo() {
    try {
        showToast('Отправка заявок...', 'info');
        
        const response = await fetch('/api/admin/send-to-amo', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ student_ids: null })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const successCount = data.results?.success?.length || 0;
            const failedCount = data.results?.failed?.length || 0;
            
            if (successCount > 0) {
                showToast(`Отправлено ${successCount} заявок`, 'success');
            }
            if (failedCount > 0) {
                showToast(`Не удалось отправить ${failedCount} заявок`, 'error');
            }
            if (successCount === 0 && failedCount === 0) {
                showToast('Нет заявок для отправки', 'info');
            }
            
            loadStats();
            loadStudents();
        } else {
            showToast(data.detail || 'Ошибка отправки', 'error');
        }
    } catch (error) {
        showToast('Ошибка подключения', 'error');
    }
}

// Export to CSV
async function exportToCSV() {
    try {
        showToast('Подготовка экспорта...', 'info');
        
        // Получаем текущие фильтры
        const filterValue = filterSelect.value;
        const searchValue = searchInput.value.trim();
        
        // Формируем URL с параметрами фильтрации
        let url = '/api/admin/export-csv';
        const params = [];
        
        if (filterValue !== '') {
            params.push(`sent_to_amo=${filterValue}`);
        }
        if (searchValue) {
            params.push(`search=${encodeURIComponent(searchValue)}`);
        }
        
        if (params.length > 0) {
            url += '?' + params.join('&');
        }
        
        // Загружаем CSV файл
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            // Получаем blob и создаем ссылку для скачивания
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = downloadUrl;
            
            // Получаем имя файла из заголовка Content-Disposition
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'export.csv';
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i);
                if (filenameMatch) {
                    filename = filenameMatch[1];
                }
            }
            
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(downloadUrl);
            
            showToast('CSV файл успешно выгружен', 'success');
        } else {
            const data = await response.json();
            showToast(data.detail || 'Ошибка экспорта', 'error');
        }
    } catch (error) {
        console.error('Export error:', error);
        showToast('Ошибка подключения', 'error');
    }
}

// Verify AMO status
async function verifyAmoStatus() {
    try {
        showToast('Проверка заявок в AMO...', 'info');
        
        // Проверяем все заявки с amo_lead_id (включая помеченные как неотправленные)
        // чтобы восстановить статусы тех, что были неправильно помечены
        const response = await fetch('/api/admin/verify-amo?check_all=true', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const checked = data.results?.checked || 0;
            const updated = data.results?.updated || 0;
            const notFound = data.results?.not_found?.length || 0;
            const wrongPipeline = data.results?.wrong_pipeline?.length || 0;
            const hidden = data.results?.hidden?.length || 0;
            
            if (updated > 0) {
                // Формируем детальное сообщение
                const issues = [];
                if (notFound > 0) issues.push(`не найдено: ${notFound}`);
                if (wrongPipeline > 0) issues.push(`неправильная воронка: ${wrongPipeline}`);
                if (hidden > 0) issues.push(`скрытые: ${hidden}`);
                
                const issuesText = issues.length > 0 ? issues.join(', ') : 'проблемы обнаружены';
                showToast(
                    `Проверено ${checked} заявок. ${issuesText}. Обновлено: ${updated}.`,
                    'warning'
                );
            } else {
                showToast(
                    `Проверено ${checked} заявок. Все заявки найдены в правильной воронке.`,
                    'success'
                );
            }
            
            // Обновляем статистику и список
            loadStats();
            loadStudents();
        } else {
            showToast(data.detail || 'Ошибка проверки', 'error');
        }
    } catch (error) {
        console.error('Verify AMO error:', error);
        showToast('Ошибка подключения', 'error');
    }
}

// Delete functions
function confirmDelete(studentId) {
    deleteStudentId = studentId;
    document.getElementById('deleteModal').classList.add('active');
    document.getElementById('confirmDelete').onclick = () => deleteStudent();
}

function closeModal() {
    document.getElementById('deleteModal').classList.remove('active');
    deleteStudentId = null;
}

// Edit lead modal
function openEditModal(event) {
    if (event.target.closest('.action-buttons')) return;
    const row = event.currentTarget;
    const studentId = row && row.dataset && row.dataset.studentId;
    if (!studentId) return;
    editStudentId = studentId;
    document.getElementById('editModal').classList.add('active');
    loadStudentForEdit(studentId);
}

function closeEditModal() {
    document.getElementById('editModal').classList.remove('active');
    editStudentId = null;
}

async function loadStudentForEdit(studentId) {
    try {
        const response = await fetch(`/api/admin/students/${studentId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить данные');
        const student = await response.json();
        document.getElementById('editLeadFio').value = student.fio || '';
        document.getElementById('editLeadSchool').value = student.school || '';
        document.getElementById('editLeadClass').value = student.class || '';
        document.getElementById('editLeadPhone').value = student.phone || '';
        document.getElementById('editLeadParentName').value = student.parent_name || '';
        document.getElementById('editLeadParentPhone').value = student.parent_phone || '';
    } catch (err) {
        showToast(err.message || 'Ошибка загрузки заявки', 'error');
        closeEditModal();
    }
}

async function saveEdit(event) {
    event.preventDefault();
    if (!editStudentId) return;
    const fio = document.getElementById('editLeadFio').value.trim();
    const school = document.getElementById('editLeadSchool').value.trim();
    const studentClass = document.getElementById('editLeadClass').value.trim();
    const phone = document.getElementById('editLeadPhone').value.trim();
    const parentName = document.getElementById('editLeadParentName').value.trim();
    const parentPhone = document.getElementById('editLeadParentPhone').value.trim();
    if (!fio || !school || !studentClass || !phone) {
        showToast('Заполните ФИО, школу, класс и телефон', 'error');
        return;
    }
    try {
        const params = new URLSearchParams({
            fio, school, student_class: studentClass, phone,
            parent_name: parentName || '',
            parent_phone: parentPhone || ''
        });
        const response = await fetch(`/api/admin/students/${editStudentId}?${params}`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            showToast('Заявка сохранена', 'success');
            closeEditModal();
            loadStats();
            loadStudents();
        } else {
            const data = await response.json();
            showToast(data.detail || 'Ошибка сохранения', 'error');
        }
    } catch (err) {
        showToast('Ошибка подключения', 'error');
    }
}

async function deleteStudent() {
    if (!deleteStudentId) return;
    
    try {
        const response = await fetch(`/api/admin/students/${deleteStudentId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            showToast('Заявка удалена', 'success');
            closeModal();
            loadStats();
            loadStudents();
        } else {
            const data = await response.json();
            showToast(data.detail || 'Ошибка удаления', 'error');
        }
    } catch (error) {
        showToast('Ошибка подключения', 'error');
    }
}

// Utility functions
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeEditModal();
    }
});

// Close modal on overlay click
document.getElementById('deleteModal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeModal();
    }
});
document.getElementById('editModal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeEditModal();
    }
});

