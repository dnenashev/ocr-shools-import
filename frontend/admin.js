// State
let token = localStorage.getItem('admin_token');
let currentPage = 0;
let pageSize = 20;
let totalStudents = 0;
let currentFilter = '';
let searchQuery = '';
let deleteStudentId = null;

// DOM Elements
const loginPage = document.getElementById('loginPage');
const adminPanel = document.getElementById('adminPanel');
const loginForm = document.getElementById('loginForm');
const studentsTable = document.getElementById('studentsTable');
const searchInput = document.getElementById('searchInput');
const filterSelect = document.getElementById('filterSelect');
const toastContainer = document.getElementById('toastContainer');

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
            <td colspan="7">
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
            renderStudents(data.students);
            updatePagination();
        } else if (response.status === 401) {
            logout();
        }
    } catch (error) {
        console.error('Error loading students:', error);
        studentsTable.innerHTML = `
            <tr>
                <td colspan="8">
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
                <td colspan="8">
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
        
        return `
        <tr>
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
            <td>
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
    loadStudents();
}

// Search and Filter
function handleSearch() {
    searchQuery = searchInput.value.trim();
    currentPage = 0;
    loadStudents();
}

function handleFilter() {
    currentFilter = filterSelect.value;
    currentPage = 0;
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
    }
});

// Close modal on overlay click
document.getElementById('deleteModal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeModal();
    }
});

