// Search functionality for MBA Wiki

document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.querySelector('.search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSearch);
    }

    // Add keyboard shortcut: "/" to focus search
    document.addEventListener('keydown', function(event) {
        if (event.key === '/' && !isInputFocused()) {
            event.preventDefault();
            const searchInput = document.querySelector('.search-input');
            if (searchInput) {
                searchInput.focus();
            }
        }
    });
});

function handleSearch(event) {
    const query = event.target.querySelector('.search-input').value.trim();

    if (!query) {
        event.preventDefault();
        return false;
    }

    // Store query for results page if needed
    sessionStorage.setItem('lastSearchQuery', query);

    return true;
}

function isInputFocused() {
    const active = document.activeElement;
    return active && (
        active.tagName === 'INPUT' ||
        active.tagName === 'TEXTAREA' ||
        active.contentEditable === 'true'
    );
}

// Highlight wikilinks on page load
function highlightWikilinks() {
    const links = document.querySelectorAll('.wikilink');
    links.forEach(link => {
        link.addEventListener('mouseenter', function() {
            this.style.borderBottom = '2px solid #0645ad';
        });
        link.addEventListener('mouseleave', function() {
            this.style.borderBottom = 'none';
        });
    });

    const brokenLinks = document.querySelectorAll('.broken-wikilink');
    brokenLinks.forEach(link => {
        link.addEventListener('mouseenter', function() {
            this.style.backgroundColor = '#fee';
        });
        link.addEventListener('mouseleave', function() {
            this.style.backgroundColor = 'transparent';
        });
    });
}

// Call on page load
document.addEventListener('DOMContentLoaded', highlightWikilinks);
