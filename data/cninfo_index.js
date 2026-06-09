!function () {
    
}

function handleExNoHead(i, name) {
    var _this = $('.faqs-item-imager .imger'+i);
    var css = {
        height: '20px',
        width: '20px',
        bgcolor: '#e6f0ff',
        color: 'rgba(69, 130, 255, 0.44)',
        borderRadius: '50%',
        fontSize: '12px',
        fontWeight: '',
        display: 'inline-block',
        marginRight: '4px',
        textAlign: 'center'
    };
    handleHeadImage(_this, css, name);
}

//æ å¾çå¤çï¼
function handleHeadImage(_this, css, name) {
    name = name.trim();
    name = name ? name.substring(0,1) : '-';
    if(_this.attr('class') != undefined){

    }
    var classList = _this.attr('class') == undefined ?'':_this.attr('class');
    var html = '<div class="common-head '+ classList + '">'
        +'<span>'+ name +'</span>'
        +'</div>';
    _this.after(html);
    _this.next().css({
        'height': css.height,
        'line-height': css.height,
        'width': css.width,
        'background-color': css.bgcolor,
        'border-radius': css.borderRadius,
        'font-weight': css.fontWeight,
        'margin': css.margin,
        'float': css.float,
        'display': css.display,
        'margin-right': css.marginRight,
        'text-align': css.textAlign
    });
    _this.next().find('span').css({
        'line-height': css.height,
        'font-size': css.fontSize,
        'color': css.color
    });
    //_this.css('display','none');
    _this.remove();
    _this.next().css('display', 'inline-block');
}
