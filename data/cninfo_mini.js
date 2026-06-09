// JavaScript Document
(function($){

    var userAgent = window.navigator.userAgent.toLowerCase(),
        document = window.document,
        toString = Object.toString;

    function mini() {};
    $.extend(mini, {
        webroot: window.location.protocol + "//" + window.location.host,
        browser: {
            version: (userAgent.match(/.+(?:rv|it|ra|ie)[\/: ]([\d.]+)/) || [])[1],
            isFirefox: /firefox/i.test(userAgent),
            isSafari: /webkit/i.test(userAgent),
            isOpera: /opera/i.test(userAgent),
            isIE: /msie/i.test(userAgent) && !/operai/.test(userAgent),
            isMozilla: /mozilla/i.test(userAgent) && !/(compatible|webkit)/i.test(userAgent),
            isIE6: /msie/i.test(userAgent) && !/opera/i.test(userAgent) && ((userAgent.match(/.+(?:rv|it|ra|ie)[\/: ]([\d.]+)/) || [])[1] < 7)
        },
        platform: {
            isIphone: /iPhone/i.test(userAgent),
            isIpod: /iPod/i.test(userAgent),
            isAndroid: /android/i.test(userAgent),
            isIos: /(iPhone|iPod|Mac|ios)/i.test(userAgent),
            isApple: /(iPhone|iPod|Mac|ios)/i.test(userAgent),
            isMobile: /(iPhone|iPod|ios|android)/i.test(userAgent)
        },
        extendClass: function(baseClass, prop) {
            var This = this;
            if (typeof(baseClass) === "object") {
                prop = baseClass;
                baseClass = null
            }
            function F() {
                // å¦æç¶ç±»å­å¨ï¼åå®ä¾å¯¹è±¡çbaseprototypeæåç¶ç±»çååq
                // è¿å°±æä¾äºå¨å®ä¾å¯¹è±¡ä¸­è°ç¨ç¶ç±»æ¹æ³çéå¾
                if (baseClass) {
                    this.baseprototype = baseClass.prototype;
                }
                this.init.apply(this, arguments);
            }

            // å¦ææ­¤ç±»éè¦ä»å¶å®ç±»æ©å±
            if (baseClass) {
                var middleClass = function() {};
                middleClass.prototype = baseClass.prototype;
                F.prototype = new middleClass();
                F.prototype.constructor = F;
            }

            // è¦çç¶ç±»çååå½æ°
            for (var name in prop) {
                if (prop.hasOwnProperty(name)) {
                    if (baseClass && typeof(prop[name]) === "function" && This.argumentNames(prop[name])[0] === "$super") {
                        F.prototype[name] = (function(name, fn) {
                            return function() {
                                var that = this;
                                $super = function() {
                                    return baseClass.prototype[name].apply(that, arguments)
                                };
                                return fn.apply(this, Array.prototype.concat.apply($super, arguments))
                            }
                        })(name, prop[name])
                    } else {
                        F.prototype[name] = prop[name]
                    }
                }
            }
            return F
        },
        serializeObj: function(form) {
            var seriaData = $(form).serializeArray(),
                countData = {},
                formData = {};
            if (seriaData) {
                for (var i in seriaData) {
                    if (countData[seriaData[i]['name']]) {
                        countData[seriaData[i]['name']] += 1;
                        formData[seriaData[i]['name']] = []
                    } else {
                        countData[seriaData[i]['name']] = 1
                    }
                }
                for (var i in seriaData) {
                    if (countData[seriaData[i]['name']] > 1) {
                        formData[seriaData[i]['name']].push(seriaData[i]['value'])
                    } else {
                        formData[seriaData[i]['name']] = seriaData[i]['value']
                    }
                }
            }
            return formData
        },
        getExp: function(type) {
            if (!type) {
                return null
            }
            switch (type) {
                case 'safe':
                    return /^[\u4E00-\u9FFFa-zA-Z0-9~@#%!_\.+-]+$/;
                    break;
                case 'zh':
                    return /^[\u4E00-\u9FFF]+$/;
                    break;
                case 'email':
                    return /^[0-9a-z][a-z0-9\._-]{1,}@[a-z0-9-]{1,}[a-z0-9]\.[a-z\.]{1,}[a-z]$/;
                    break;
                case 'website':
                    return /^(http|https|ftp):\/\/[A-za-z0-9\.\-_~@#?=&:\/]+$/;
                    break;
                case 'number':
                    return /^[0-9\.]+$/;
                    break;
                case 'id':
                    return /^(\d{15}$|^\d{18}$|^\d{17}(\d|X|x))$/;
                case 'tel':
                    return /^[0-9\#\-\+\s]{6,20}$/;
                    break;
                case 'phone':
                case 'mobile':
                    return /^1[3-9]\d{9}$/;
                    break;
                case 'username':
                    return /^[A-Za-z]{1}[a-zA-Z0-9~@#%!_+-\.]{5,50}$/ && !/^[A-Za-z]$/ && !/^[0-9]$/;
                    break;
                case 'password':
                    return /^[A-Za-z]{1}[a-zA-Z0-9~@#%!_+-\.]{5,50}$/;
                    break;
                default:
                    if (/\/([\s\S]+?)\/([A-Za-z]+)?/.test(type)) {
                        var option = type.substr(type.lastIndexOf('/') + 1),
                            regexp = type.substr(1, type.lastIndexOf('/') - 1);
                        return new RegExp(regexp, option)
                    } else {
                        return new RegExp('^' + type + '$')
                    }
            }
        },
        test: function(testStr, type) {
            var EXP = this.getExp(type);
            return EXP ? EXP.test(testStr) : true
        },
        formatEvent: function(oEvent) {
            if (oEvent && (oEvent.keyCode || oEvent.target || oEvent.srcElement)) {
                if (/msie/.test(userAgent)) {
                    var doc = document.documentElement,
                        body = document.body;
                    oEvent.charCode = (oEvent.type == "keypress") ? oEvent.keyCode : 0;
                    oEvent.eventPhase = 2;
                    oEvent.isChar = (oEvent.charCode > 0);
                    oEvent.pageX = oEvent.clientX + (doc && doc.scrollLeft || body && body.scrollLeft || 0) - (doc && doc.clientLeft || body && body.clientLeft || 0);
                    oEvent.pageY = oEvent.clientY + (doc && doc.scrollTop || body && body.scrollTop || 0) - (doc && doc.clientTop || body && body.clientTop || 0);
                    if (oEvent.type == "mouseout") {
                        oEvent.relatedTarget = oEvent.toElement
                    } else if (oEvent.type == "mouseover") {
                        oEvent.relatedTarget = oEvent.fromElement
                    }
                    oEvent.preventDefault = function() {
                        oEvent.returnValue = false
                    };
                    oEvent.stopPropagation = function() {
                        oEvent.cancelBubble = true
                    };
                    oEvent.target = oEvent.srcElement || document;
                    oEvent.target.nodeType === 3 && (oEvent.target = oEvent.target.parentNode);
                    oEvent.time = (new Date()).getTime();
                    oEvent.stopDefault = function(stopEvent) {
                        oEvent.returnValue = false;
                        stopEvent && (oEvent.cancelBubble = true)
                    };
                    oEvent.stopEvent = function(stopDefault) {
                        stopDefault && (oEvent.returnValue = false);
                        oEvent.cancelBubble = true
                    };
                    oEvent.stop = function() {
                        oEvent.returnValue = false;
                        oEvent.cancelBubble = true
                    }
                } else {
                    oEvent.stopDefault = function(stopEvent) {
                        oEvent.preventDefault();
                        stopEvent && oEvent.stopPropagation()
                    };
                    oEvent.stopEvent = function(stopDefault) {
                        stopDefault && oEvent.preventDefault();
                        oEvent.stopPropagation()
                    };
                    oEvent.stop = function() {
                        oEvent.preventDefault();
                        oEvent.stopPropagation()
                    }
                }
                return oEvent
            }
            return null
        },
        getEvent: function() {
            var byEvent = this.formatEvent(window.event ? window.event : (arguments.callee.caller.arguments ? arguments.callee.caller.arguments[0] : null));
            return byEvent ? byEvent : {
                stop: function() {},
                stopEvent: function() {},
                stopDefault: function() {}
            }
        },
        getExpiresDay: function(a) {
            return new Date(new Date().getTime() + (a ? a : 1) * 24 * 3600 * 1000)
        },
        setCookie: function(name, value, expires, path, domain) {
            if (typeof expires == "undefined") {
                expires = new Date(new Date().getTime() + 24 * 3600 * 1000)
            }
            document.cookie = name + "=" + escape(value) + ((expires) ? "; expires=" + expires.toGMTString() : "") + ((path) ? "; path=" + path : "; path=/") + ((domain) ? ";domain=" + domain : "")
        },
        getCookie: function(name) {
            var arr = document.cookie.match(new RegExp("(^| )" + name + "=([^;]*)(;|$)"));
            return arr != null ? unescape(arr[2]) : null
        },
        clearCookie: function(name, path, domain) {
            if (this.getCookie(name)) {
                document.cookie = name + "=" + ((path) ? "; path=" + path : "; path=/") + ((domain) ? "; domain=" + domain : "") + ";expires=Fri, 02-Jan-1970 00:00:00 GMT"
            }
        },
        loadJs: function(url, callback, charset) {
            var allScripts = $('script'),
                script = null,
                hasScript = 0;
            allScripts.each(function(index, element) {
                if (element.src.indexOf(url) > -1) {
                    hasScript = 1;
                    script = element
                }
            });
            if (!hasScript) {
                var script = document.createElement("script");
                script.type = "text/javascript";
                if (charset) {
                    script.setAttribute("charset", charset ? charset : 'utf-8')
                }
                if (script.readyState) {
                    script.onreadystatechange = function() {
                        if (script.readyState == "loaded" || script.readyState == "complete") {
                            script.onreadystatechange = null;
                            callback && callback()
                        }
                    }
                } else {
                    script.onload = function() {
                        callback && callback()
                    }
                }
                script.src = url + (url.indexOf('?') != -1 ? '&' : '?') + 'r=' + Math.random();
                document.getElementsByTagName("head")[0].appendChild(script)
            } else {
                callback && callback()
            }
            return script
        },
        loadCss: function(url, callback, charset) {
            var allcss = $('link'),
                css = null,
                hascss = 0;
            allcss.each(function(index, element) {
                if (element.href.indexOf(url) > -1) {
                    hascss = 1;
                    css = element
                }
            });
            if (!hascss) {
                var css = document.createElement("link");
                css.type = "text/css";
                css.rel = "stylesheet";
                css.href = url + (url.indexOf('?') != -1 ? '&' : '?') + 'r=' + Math.random();
                if (charset) {
                    css.setAttribute("charset", charset ? charset : 'utf-8')
                }
                document.getElementsByTagName("head")[0].appendChild(css);
                callback && callback()
            } else {
                callback && callback()
            }
            return css
        },
        concatUrl: function(cname, cvalue, url, index) {
            var url = !url || url == '' ? this.getAllUrl() : url,
                name = encodeURIComponent(cname),
                value = cvalue ? encodeURIComponent(cvalue) : '',
                index = index ? index : 'index.php',
                reg = new RegExp('([&\\?])' + name + '((=[^&]*)|(&)|$)');
            if (!name) {
                return url
            }
            url = url.replace(/([^#]*)[#]+$/, '$1');
            if (cvalue === null) {
                return url.replace(reg, '$1$4')
            }
            if (reg.test(url)) {
                url = url.replace(reg, (value || value === 0 ? '$1' + name + '=' + value + '$4' : '$1' + name + '$4'))
            } else if (value || value === 0) {
                if (url.indexOf('?') < 0) {
                    url = url + '?' + name + '=' + value
                } else {
                    url = url + '&' + name + '=' + value
                }
            } else if (cname) {
                if (url.indexOf('?') < 0) {
                    url = url + '?' + cname
                } else {
                    url = url + '&' + cname
                }
            }
            url = url.replace(/[\/\&\#]$/, '');
            return url
        },
        bindAutoHeight: function(selector, style, siblings) {
            var style = style ? style : 'min-height',
                siblings = siblings ? siblings : 'div',
                selector = selector ? selector : '#content',
                autoHeight = function() {
                    $(selector).css(style, 'auto').each(function() {
                        var parent = $(this).parent(),
                            siblings = $(this).siblings(siblings),
                            minHeight = 0;
                        siblings.each(function() {
                            var postion = $(this).css('position');
                            if (!postion || postion == 'static' || postion == 'relative') {
                                minHeight += $(this).outerHeight(true)
                            }
                        });
                        $(this).css(style, Math.max((parent.height() - minHeight), 0))
                    })
                };
            $(window).bind('resize.autoHeight', autoHeight).resize()
        },
        loadImg: function(imgUrl, loaded, ready, error) {
            if (!imgUrl) {
                return false
            }
            var This = this,
                newImg = new Image(),
                imgCheck = null;
            newImg.src = imgUrl;
            if (newImg.complete) {
                ready && ready(imgUrl, newImg.width, newImg.height);
                loaded && loaded(imgUrl, newImg.width, newImg.height);
                return
            };
            if (ready) {
                var width = newImg.width,
                    height = newImg.height;
                imgCheck = function() {
                    try {
                        newWidth = newImg.width;
                        newHeight = newImg.height;
                        if (newWidth !== width || newHeight !== height || newWidth * newHeight > 1024) {
                            ready && ready(imgUrl, newImg.width, newImg.height);
                            imgCheck.end = true
                        }
                    } catch (e) {
                        ready && ready(imgUrl, newImg.width, newImg.height);
                        imgCheck.end = true
                    }
                };
                imgCheck.end = false;
                imgCheck()
            }
            newImg.onerror = function() {
                error && error(imgUrl);
                newImg = newImg.onload = newImg.onerror = null;
                imgCheck && (imgCheck.end = true)
            };
            newImg.onload = function() {
                ready && ready(imgUrl, newImg.width, newImg.height);
                loaded && loaded(imgUrl, newImg.width, newImg.height);
                newImg = newImg.onload = newImg.onerror = null;
                imgCheck && (imgCheck.end = true)
            };
            if (ready && !imgCheck.end) {
                This.imgLoad.push(imgCheck);
                if (This.imgLoadListen === null) {
                    This.imgLoadListen = setInterval(function() {
                        This.imgLoadTick()
                    }, 50)
                }
            }
        },
        loadImgs: function(imgUrls, callback) {
            var This = this;
            if (!imgUrls) {
                return false
            }
            if (!$.isArray(imgUrls)) {
                if (typeof imgUrls == 'string' && (imgUrls.indexOf('.gif') > -1 || imgUrls.indexOf('.jpg') > -1 || imgUrls.indexOf('.png') > -1 || imgUrls.indexOf('.bmp') > -1)) {
                    imgUrls = imgUrls.split(';')
                } else {
                    var tempUrls = [];
                    $(imgUrls).add($(imgUrls).find('img,div')).each(function() {
                        var _src = $(this).attr('src'),
                            _image = $(this).css('background-image');
                        if (_src && _src != '') {
                            tempUrls.push(_src)
                        } else if (_image && _image.indexOf('url') > -1) {
                            tempUrls.push(_image.replace(/^url\(|\)$/gi, '').replace(/^['"]|["']$/gi, ""))
                        }
                    });
                    imgUrls = tempUrls
                }
            }
            if ($.isArray(imgUrls) && imgUrls.length > 0) {
                for (ii in imgUrls) {
                    if (!imgUrls[ii]) {
                        imgUrls.splice(ii, 1)
                    }
                }
                if (imgUrls.length > 0) {
                    var imgLength = imgUrls.length,
                        imgCount = 1,
                        imgCkeck = function() {
                            if (imgLength == imgCount++) {
                                callback && callback(imgLength)
                            }
                        };
                    for (ii in imgUrls) {
                        This.loadImg(imgUrls[ii], imgCkeck, null, imgCkeck)
                    }
                } else {
                    callback && callback(0)
                }
            } else {
                callback && callback(0)
            }
        },
        addTouchEvevt: function(touchListen, touchObj, liveEvent) {
            if (!("ontouchend" in document)) {
                return false
            }
            var This = this,
                liveEvent = liveEvent ? 1 : 0,
                touchObj = touchObj ? $(touchObj) : $(document),
                touchListen = $.extend({
                    'moveSize': 0,
                    'moveLeft': null,
                    'moveUp': null,
                    'moveRight': null,
                    'moveDown': null,
                    'move': null,
                    'touchStart': null,
                    'touchEnd': null,
                    'fllowTouch': false,
                    'fllowStyle': 'margin',
                    'fllowType': 'x',
                    'fllowX': 0,
                    'fllowY': 0,
                    'touchX': 0,
                    'touchY': 0,
                    'moveX': 0,
                    'moveY': 0
                }, touchListen);
            touchListen.fllowStyle = touchListen.fllowStyle.toLowerCase();
            touchListen.fllowType = touchListen.fllowType.toLowerCase();
            touchListen.fllowStyle = touchListen.fllowStyle == 'margin' ? 'margin-' : '';
            touchListen.fllowType = touchListen.fllowType == 'x' || touchListen.fllowType == 'y' || touchListen.fllowType == 'xy' ? touchListen.fllowType : 'x';
            var touchStart = function(event) {
                try {
                    var _evt = This.getEvent(),
                        _target = $(this),
                        touch = _evt.targetTouches[0];
                    touchListen.touchX = Number(touch.pageX);
                    touchListen.touchY = Number(touch.pageY);
                    touchListen.fllowX = parseInt($(_target).css(touchListen.fllowStyle + 'left'));
                    touchListen.fllowY = parseInt($(_target).css(touchListen.fllowStyle + 'top'));
                    if ($.isFunction(touchListen.touchStart)) {
                        touchListen.touchStart(touchListen.touchX, touchListen.touchY, $(this))
                    }
                    event.preventDefault()
                } catch (e) {}
            };
            var touchMove = function(event) {
                try {
                    var _evt = This.getEvent(),
                        _target = $(this),
                        touch = _evt.targetTouches[0];
                    touchListen.moveX = Number(touch.pageX) - touchListen.touchX;
                    touchListen.moveY = Number(touch.pageY) - touchListen.touchY;
                    if (touchListen.fllowTouch) {
                        switch (touchListen.fllowType) {
                            case 'x':
                                $(_target).css(touchListen.fllowStyle + 'left', touchListen.fllowX + touchListen.moveX);
                                break;
                            case 'y':
                                $(_target).css(touchListen.fllowStyle + 'top', touchListen.fllowY + touchListen.moveY);
                                break;
                            case 'xy':
                                $(_target).css(touchListen.fllowStyle + 'left', touchListen.fllowX + touchListen.moveX);
                                $(_target).css(touchListen.fllowStyle + 'top', touchListen.fllowY + touchListen.moveY);
                                break
                        }
                    }
                    if ($.isFunction(touchListen.move)) {
                        touchListen.move(touchListen.moveX, touchListen.moveY, $(this))
                    }
                    event.preventDefault()
                } catch (e) {}
            };
            var touchEnd = function(event) {
                try {
                    var _evt = This.getEvent();
                    if (Math.abs(touchListen.moveX) >= parseInt(touchListen.moveSize)) {
                        if (touchListen.moveX > 0) {
                            if ($.isFunction(touchListen.moveRight)) {
                                touchListen.moveRight(touchListen.moveX, $(this))
                            }
                        } else if (touchListen.moveX < 0) {
                            if ($.isFunction(touchListen.moveLeft)) {
                                touchListen.moveLeft(touchListen.moveX, $(this))
                            }
                        }
                    }
                    if (Math.abs(touchListen.moveY) >= parseInt(touchListen.moveSize)) {
                        if (touchListen.moveY > 0) {
                            if ($.isFunction(touchListen.moveDown)) {
                                touchListen.moveDown(touchListen.moveY, $(this))
                            }
                        } else if (touchListen.moveY < 0) {
                            if ($.isFunction(touchListen.moveUp)) {
                                touchListen.moveUp(touchListen.moveY, $(this))
                            }
                        }
                    }
                    if ($.isFunction(touchListen.touchEnd)) {
                        touchListen.touchEnd(touchListen.moveX, touchListen.moveY, $(this))
                    }
                    touchListen.touchX = touchListen.touchY = touchListen.moveX = touchListen.moveY = touchListen.fllowX = touchListen.fllowY = 0;
                    event.preventDefault()
                } catch (e) {}
            };
            if (liveEvent) {
                touchObj.live('touchstart', touchStart);
                touchObj.live('touchmove', touchMove);
                touchObj.live('touchend', touchEnd)
            } else {
                touchObj.bind('touchstart', touchStart);
                touchObj.bind('touchmove', touchMove);
                touchObj.bind('touchend', touchEnd)
            }
        },
        toAnimate: function(setStr, overNumber, suffix, speed, overFunc) {
            var begainValue = 0,
                overNumber = parseInt(overNumber),
                marginValue = 0,
                t = 0,
                d = this.getSpeed(speed),
                fun = this.tween.getFun();
            eval("begainValue=parseInt(" + setStr + ")");
            marginValue = overNumber - begainValue;

            function runAnimate() {
                if (t < d) {
                    t++;
                    eval(setStr + "=" + (begainValue + fun(t, 0, marginValue, d)));
                    setTimeout(runAnimate, 10)
                } else {
                    eval(setStr + "=" + overNumber);
                    overFunc && overFunc()
                }
            }
            runAnimate()
        },
        setTween: function(tweenType, easeType) {
            if (tweenType) {
                this.tween.tweenType = tweenType
            }
            if (easeType) {
                this.tween.easeType = easeType
            }
        },
        tween: {
            tweenType: 'Quint',
            easeType: 'easeInOut',
            getFun: function(tween, ease) {
                tween = tween ? tween : this.tweenType;
                ease = ease ? ease : this.easeType;
                return tween == "Linear" ? this.Linear : this[tween][ease]
            },
            Linear: function(t, b, c, d) {
                return c * t / d + b
            },
            Quad: {
                easeIn: function(t, b, c, d) {
                    return c * (t /= d) * t + b
                },
                easeOut: function(t, b, c, d) {
                    return -c * (t /= d) * (t - 2) + b
                },
                easeInOut: function(t, b, c, d) {
                    return ((t /= d / 2) < 1) ? (c / 2 * t * t + b) : (-c / 2 * ((--t) * (t - 2) - 1) + b)
                }
            },
            Cubic: {
                easeIn: function(t, b, c, d) {
                    return c * (t /= d) * t * t + b
                },
                easeOut: function(t, b, c, d) {
                    return c * ((t = t / d - 1) * t * t + 1) + b
                },
                easeInOut: function(t, b, c, d) {
                    return ((t /= d / 2) < 1) ? (c / 2 * t * t * t + b) : (c / 2 * ((t -= 2) * t * t + 2) + b)
                }
            },
            Quart: {
                easeIn: function(t, b, c, d) {
                    return c * (t /= d) * t * t * t + b
                },
                easeOut: function(t, b, c, d) {
                    return -c * ((t = t / d - 1) * t * t * t - 1) + b
                },
                easeInOut: function(t, b, c, d) {
                    return ((t /= d / 2) < 1) ? (c / 2 * t * t * t * t + b) : (-c / 2 * ((t -= 2) * t * t * t - 2) + b)
                }
            },
            Quint: {
                easeIn: function(t, b, c, d) {
                    return c * (t /= d) * t * t * t * t + b
                },
                easeOut: function(t, b, c, d) {
                    return c * ((t = t / d - 1) * t * t * t * t + 1) + b
                },
                easeInOut: function(t, b, c, d) {
                    return ((t /= d / 2) < 1) ? (c / 2 * t * t * t * t * t + b) : (c / 2 * ((t -= 2) * t * t * t * t + 2) + b)
                }
            },
            Sine: {
                easeIn: function(t, b, c, d) {
                    return -c * Math.cos(t / d * (Math.PI / 2)) + c + b
                },
                easeOut: function(t, b, c, d) {
                    return c * Math.sin(t / d * (Math.PI / 2)) + b
                },
                easeInOut: function(t, b, c, d) {
                    return -c / 2 * (Math.cos(Math.PI * t / d) - 1) + b
                }
            },
            Expo: {
                easeIn: function(t, b, c, d) {
                    return (t == 0) ? b : c * Math.pow(2, 10 * (t / d - 1)) + b
                },
                easeOut: function(t, b, c, d) {
                    return (t == d) ? b + c : c * (-Math.pow(2, -10 * t / d) + 1) + b
                },
                easeInOut: function(t, b, c, d) {
                    if (t == 0) {
                        return b
                    }
                    if (t == d) {
                        return b + c
                    }
                    return ((t /= d / 2) < 1) ? (c / 2 * Math.pow(2, 10 * (t - 1)) + b) : (c / 2 * (-Math.pow(2, -10 * --t) + 2) + b)
                }
            },
            Circ: {
                easeIn: function(t, b, c, d) {
                    return -c * (Math.sqrt(1 - (t /= d) * t) - 1) + b
                },
                easeOut: function(t, b, c, d) {
                    return c * Math.sqrt(1 - (t = t / d - 1) * t) + b
                },
                easeInOut: function(t, b, c, d) {
                    return ((t /= d / 2) < 1) ? (-c / 2 * (Math.sqrt(1 - t * t) - 1) + b) : (c / 2 * (Math.sqrt(1 - (t -= 2) * t) + 1) + b)
                }
            },
            Elastic: {
                easeIn: function(t, b, c, d, a, p) {
                    if (t == 0) return b;
                    if ((t /= d) == 1) return b + c;
                    if (!p) p = d * .3;
                    if (!a || a < Math.abs(c)) {
                        a = c;
                        var s = p / 4
                    } else var s = p / (2 * Math.PI) * Math.asin(c / a);
                    return -(a * Math.pow(2, 10 * (t -= 1)) * Math.sin((t * d - s) * (2 * Math.PI) / p)) + b
                },
                easeOut: function(t, b, c, d, a, p) {
                    if (t == 0) return b;
                    if ((t /= d) == 1) return b + c;
                    if (!p) p = d * .3;
                    if (!a || a < Math.abs(c)) {
                        a = c;
                        var s = p / 4
                    } else var s = p / (2 * Math.PI) * Math.asin(c / a);
                    return (a * Math.pow(2, -10 * t) * Math.sin((t * d - s) * (2 * Math.PI) / p) + c + b)
                },
                easeInOut: function(t, b, c, d, a, p) {
                    if (t == 0) return b;
                    if ((t /= d / 2) == 2) return b + c;
                    if (!p) p = d * (.3 * 1.5);
                    if (!a || a < Math.abs(c)) {
                        a = c;
                        var s = p / 4
                    } else var s = p / (2 * Math.PI) * Math.asin(c / a);
                    if (t < 1) return -.5 * (a * Math.pow(2, 10 * (t -= 1)) * Math.sin((t * d - s) * (2 * Math.PI) / p)) + b;
                    return a * Math.pow(2, -10 * (t -= 1)) * Math.sin((t * d - s) * (2 * Math.PI) / p) * .5 + c + b
                }
            },
            Back: {
                easeIn: function(t, b, c, d, s) {
                    if (s == undefined) s = 1.70158;
                    return c * (t /= d) * t * ((s + 1) * t - s) + b
                },
                easeOut: function(t, b, c, d, s) {
                    if (s == undefined) s = 1.70158;
                    return c * ((t = t / d - 1) * t * ((s + 1) * t + s) + 1) + b
                },
                easeInOut: function(t, b, c, d, s) {
                    if (s == undefined) s = 1.70158;
                    if ((t /= d / 2) < 1) return c / 2 * (t * t * (((s *= (1.525)) + 1) * t - s)) + b;
                    return c / 2 * ((t -= 2) * t * (((s *= (1.525)) + 1) * t + s) + 2) + b
                }
            },
            Bounce: {
                easeIn: function(t, b, c, d) {
                    return c - mini.tween.Bounce.easeOut(d - t, 0, c, d) + b
                },
                easeOut: function(t, b, c, d) {
                    if ((t /= d) < (1 / 2.75)) {
                        return c * (7.5625 * t * t) + b
                    } else if (t < (2 / 2.75)) {
                        return c * (7.5625 * (t -= (1.5 / 2.75)) * t + .75) + b
                    } else if (t < (2.5 / 2.75)) {
                        return c * (7.5625 * (t -= (2.25 / 2.75)) * t + .9375) + b
                    } else {
                        return c * (7.5625 * (t -= (2.625 / 2.75)) * t + .984375) + b
                    }
                },
                easeInOut: function(t, b, c, d) {
                    if (t < d / 2) return mini.tween.Bounce.easeIn(t * 2, 0, c, d) * .5 + b;
                    else return mini.tween.Bounce.easeOut(t * 2 - d, 0, c, d) * .5 + c * .5 + b
                }
            }
        },
        getSpeed: function(speed) {
            speed = !speed ? 'normal' : speed;
            switch (speed) {
                case 'slow':
                    return 80;
                    break;
                case 'normal':
                    return 50;
                    break;
                case 'fast':
                    return 30;
                    break;
                default:
                    return parseInt(speed)
            }
        },
        bindScrollBanner: function(scrollData) {
            var This = this,
                scrollData = $.extend({
                    'parentObj': '#bannerObj',
                    'scrollObj': '.bannerList',
                    'scrollType': 'left',
                    'pageObj': '.bannerPage',
                    'pageLeft': '.bannerLeft',
                    'pageRight': '.bannerRight',
                    'loadingClass': 'bannerLoading',
                    'loadingListen': null,
                    'loadingLimit': 500,
                    'loadingGif': null,
                    'scrollAttr': 'margin-left',
                    'wrapObj': '#bannerWrap',
                    'autoScroll': true,
                    'timeout': 3000,
                    'speed': 50,
                    'tweenType': 'Cubic',
                    'scrollNum': 0,
                    'scrollLen': 0,
                    'scrollWidth': 0,
                    'scrollListen': null,
                    'removeScroll': function() {
                        this.loadingListen && clearTimeout(this.loadingListen);
                        this.scrollListen && clearTimeout(this.scrollListen)
                    }
                }, ($.isPlainObject(scrollData) ? scrollData : {
                    'parentObj': scrollData
                }));
            scrollData.scrollLen = $(scrollData.scrollObj).length;
            if (scrollData.scrollLen < 2 || $(scrollData.parentObj).length < 1) {
                $(scrollData.scrollObj).show();
                return false
            }
            scrollData.loadingGif = scrollData.loadingGif ? $(scrollData.loadingGif).addClass(scrollData.loadingClass).appendTo(scrollData.parentObj) : null;
            if (scrollData.scrollType != 'left' && scrollData.scrollType != 'right' && scrollData.scrollType != 'top' && scrollData.scrollType != 'bottom') {
                scrollData.scrollType = 'left'
            }
            if (scrollData.scrollType == 'left' || scrollData.scrollType == 'right') {
                $(scrollData.scrollObj).css({
                    'float': 'left',
                    'display': 'inline-block',
                    'border': 'none',
                    'margin': '0px',
                    'padding': '0px',
                    'overflow': 'hidden',
                    'position': 'relative'
                });
                scrollData.scrollAttr = scrollData.scrollAttr.replace(/(left|right|top|bottom)/gi, scrollData.scrollType)
            } else {
                $(scrollData.scrollObj).css({
                    'display': 'block',
                    'border': 'none',
                    'margin': '0px',
                    'padding': '0px',
                    'overflow': 'hidden',
                    'position': 'relative'
                });
                scrollData.scrollAttr = scrollData.scrollAttr.replace(/(left|right|top|bottom)/gi, scrollData.scrollType)
            }
            var wrapAll = $('<div id="' + scrollData.wrapObj.replace('#', '') + '"></div>');
            $(scrollData.parentObj).css({
                'position': 'relative',
                'overflow': 'hidden'
            }).append($(scrollData.scrollObj)[0].outerHTML);
            $(scrollData.scrollObj).wrapAll('<div id="' + scrollData.wrapObj.replace('#', '') + '"></div>');
            $(scrollData.wrapObj).appendTo(scrollData.parentObj);
            if (scrollData.scrollType == 'left' || scrollData.scrollType == 'right') {
                $(window).resize(function() {
                    if ($(scrollData.parentObj).is(':visible')) {
                        scrollData.scrollWidth = $(scrollData.parentObj).width();
                        $(scrollData.wrapObj).width(scrollData.scrollWidth * (scrollData.scrollLen + 2));
                        $(scrollData.scrollObj).width(scrollData.scrollWidth);
                        $(scrollData.wrapObj).css(scrollData.scrollAttr, -scrollData.scrollWidth * scrollData.scrollNum)
                    }
                }).resize()
            } else {
                $(window).resize(function() {
                    if ($(scrollData.parentObj).is(':visible')) {
                        scrollData.scrollWidth = $(scrollData.parentObj).height();
                        $(scrollData.scrollObj).height(scrollData.scrollWidth);
                        $(scrollData.wrapObj).css(scrollData.scrollAttr, -scrollData.scrollWidth * scrollData.scrollNum)
                    }
                }).resize()
            }
            var t = 0,
                d = this.getSpeed(scrollData.speed),
                startValue = 0,
                endValue = 0,
                fun = this.tween.getFun(scrollData.tweenType),
                nowScroll = null,
                onScroll = false;
            var scrollRun = function() {
                if (t < d) {
                    onScroll = true;
                    t++;
                    $(scrollData.wrapObj).css(scrollData.scrollAttr, (startValue + fun(t, 0, endValue, d)) + 'px');
                    scrollData.scrollListen = setTimeout(scrollRun, 10)
                } else {
                    endValue = scrollData.scrollNum == 0 ? 0 : startValue + endValue;
                    $(scrollData.wrapObj).css(scrollData.scrollAttr, endValue + 'px');
                    setPage();
                    t = 0;
                    onScroll = false;
                    if (scrollData.autoScroll) {
                        scrollData.scrollListen = setTimeout(function() {
                            scrollToNum(scrollData.scrollNum + 1)
                        }, scrollData.timeout)
                    }
                }
            };
            var scrollToNum = function(num) {
                if (!onScroll) {
                    scrollData.loadingListen && clearTimeout(scrollData.loadingListen);
                    scrollData.loadingGif && $(scrollData.loadingGif).hide();
                    num = num < 0 ? scrollData.scrollLen - 1 : num;
                    num = num > scrollData.scrollLen ? scrollData.scrollLen : num;
                    scrollData.scrollNum = num;
                    nowScroll = $(scrollData.scrollObj).get(scrollData.scrollNum);
                    scrollData.loadingGif && (scrollData.loadingListen = setTimeout(function() {
                        $(scrollData.loadingGif).show()
                    }, scrollData.loadingLimit));
                    This.loadImgs(nowScroll, function() {
                        scrollData.loadingListen && clearTimeout(scrollData.loadingListen);
                        scrollData.loadingGif && $(scrollData.loadingGif).hide();
                        t = 0;
                        scrollData.scrollListen && clearTimeout(scrollData.scrollListen);
                        startValue = parseInt($(scrollData.wrapObj).css(scrollData.scrollAttr));
                        endValue = -scrollData.scrollNum * scrollData.scrollWidth - startValue;
                        scrollRun();
                        scrollData.scrollNum = scrollData.scrollNum == scrollData.scrollLen ? 0 : scrollData.scrollNum;
                        setPage()
                    })
                }
            };
            var setPage = function() {
                if ($(scrollData.parentObj).find(scrollData.pageObj).length > 0) {
                    $(scrollData.parentObj).find(scrollData.pageObj).find('a').removeClass('current');
                    $(scrollData.parentObj).find(scrollData.pageObj).find('a').eq(scrollData.scrollNum).addClass('current')
                }
            };
            This.addTouchEvevt({
                'move': function(moveX, moveY, moveObj) {
                    if (!onScroll) {
                        var _newX = endValue + moveX;
                        $(scrollData.wrapObj).css(scrollData.scrollAttr, _newX + 'px')
                    }
                },
                'moveLeft': function(moveX, moveObj) {
                    var _newX = Math.abs(parseInt($(scrollData.wrapObj).css(scrollData.scrollAttr))),
                        aWidth = scrollData.scrollWidth,
                        toNum = Math.floor(_newX / aWidth),
                        toLimit = Math.floor(_newX % aWidth),
                        toMin = Math.floor(aWidth / 5);
                    if (toLimit > toMin) {
                        scrollToNum(toNum + 1)
                    } else {
                        scrollToNum(toNum)
                    }
                },
                'moveRight': function(moveX, moveObj) {
                    var _newX = Math.abs(parseInt($(scrollData.wrapObj).css(scrollData.scrollAttr))),
                        aWidth = scrollData.scrollWidth,
                        toNum = Math.floor(_newX / aWidth) + 1,
                        toLimit = aWidth - Math.floor(_newX % aWidth),
                        toMin = Math.floor(aWidth / 5);
                    if (toLimit > toMin) {
                        scrollToNum(toNum - 1)
                    } else {
                        scrollToNum(toNum)
                    }
                }
            }, scrollData.wrapObj);
            if ($(scrollData.parentObj).find(scrollData.pageObj).length > 0) {
                for (var i = 0; i < scrollData.scrollLen; i++) {
                    (function(scrolli) {
                        var addhtml = $(scrollData.scrollObj).eq(scrolli).attr('rel'),
                            addTitle = $(scrollData.scrollObj).eq(scrolli).attr('title');
                        addTitle = addTitle ? addTitle : '';
                        addhtml = addhtml ? '<table class="middle"><tr valign="top"><td><img src="' + addhtml + '" /></td></tr></table>' : (scrolli + 1);
                        var addStr = scrolli == 0 ? '<a class="current">' + addhtml + '</a>' : '<a>' + addhtml + '</a>';
                        $(addStr).attr('title', (addTitle ? addTitle : '')).appendTo($(scrollData.parentObj).find(scrollData.pageObj)).click(function() {
                            scrollToNum(scrolli)
                        })
                    })(i)
                }
            }
            if ($(scrollData.parentObj).find(scrollData.pageLeft).length > 0) {
                $(scrollData.parentObj).find(scrollData.pageLeft).click(function() {
                    scrollToNum(scrollData.scrollNum - 1)
                })
            }
            if ($(scrollData.parentObj).find(scrollData.pageRight).length > 0) {
                $(scrollData.parentObj).find(scrollData.pageRight).click(function() {
                    scrollToNum(scrollData.scrollNum + 1)
                })
            }
            setPage();
            scrollToNum(0);
            return scrollData
        },
        bindAlphaBanner: function(scrollData) {
            var This = this,
                scrollData = $.extend({
                    'parentObj': '#bannerObj',
                    'scrollObj': '.bannerList',
                    'alphaObj': '.bannerAlpha',
                    'pageObj': '.bannerPage',
                    'pageLeft': '.bannerLeft',
                    'pageRight': '.bannerRight',
                    'loadingClass': 'bannerLoading',
                    'loadingListen': null,
                    'loadingLimit': 500,
                    'loadingGif': null,
                    'startAlpha': 0,
                    'endAlpha': 1,
                    'attrTypeX': 'data-tx',
                    'attrTypeY': 'data-ty',
                    'attrStartX': 'data-sx',
                    'attrEndX': 'data-ex',
                    'attrStartY': 'data-sy',
                    'attrEndY': 'data-ey',
                    'attrStartAlpha': 'data-sa',
                    'attrEndAlpha': 'data-ea',
                    'attrStartRotate': 'data-sr',
                    'attrEndRotate': 'data-er',
                    'attrStartScale': 'data-ss',
                    'attrEndScale': 'data-es',
                    'arrtStartCss': 'data-scss',
                    'arrtEndCss': 'data-ecss',
                    'attrSpeed': 'data-s',
                    'attrTime': 'data-t',
                    'autoScroll': true,
                    'timeout': 5000,
                    'speed': 500,
                    'easing': 'swing',
                    'scrollNum': 0,
                    'scrollNow': null,
                    'scrollLen': 0,
                    'scrollListen': null,
                    'fnHandler': null,
                    'removeScroll': function() {
                        this.loadingListen && clearTimeout(this.loadingListen);
                        this.scrollListen && clearTimeout(this.scrollListen)
                    }
                }, ($.isPlainObject(scrollData) ? scrollData : {
                    'parentObj': scrollData
                }));
            scrollData.scrollLen = $(scrollData.scrollObj).length - 1;
            if (scrollData.scrollLen < 1 || $(scrollData.parentObj).length < 1) {
                return false
            }
            scrollData.loadingGif = scrollData.loadingGif ? $(scrollData.loadingGif).addClass(scrollData.loadingClass).appendTo(scrollData.parentObj) : null;
            $(scrollData.parentObj).css({
                'position': 'relative'
            });
            $(scrollData.scrollObj).css({
                'position': 'absolute',
                'display': 'block',
                'width': '100%',
                'height': '100%',
                'padding': '0px',
                'margin': '0px',
                'overflow': 'hidden',
                'left': '0px',
                'top': '0px'
            }).hide();
            var scrollToNum = function(num, isClick) {
                scrollData.loadingListen && clearTimeout(scrollData.loadingListen);
                scrollData.loadingGif && $(scrollData.loadingGif).hide();
                var oldNum = scrollData.scrollNum;
                scrollData.scrollNum = num < 0 || num > scrollData.scrollLen ? 0 : parseInt(num);
                scrollData.scrollListen && clearTimeout(scrollData.scrollListen);
                var nowScroll = $(scrollData.scrollObj).get(scrollData.scrollNum),
                    isClick = isClick ? oldNum != scrollData.scrollNum : 1;
                if (isClick && nowScroll) {
                    scrollData.loadingGif && (scrollData.loadingListen = setTimeout(function() {
                        $(scrollData.loadingGif).show()
                    }, scrollData.loadingLimit));
                    This.loadImgs(nowScroll, function() {
                        scrollData.loadingListen && clearTimeout(scrollData.loadingListen);
                        scrollData.loadingGif && $(scrollData.loadingGif).hide();
                        scrollData.scrollNow && $(scrollData.scrollNow).css('z-index', 0).animate({
                            'opacity': scrollData.startAlpha
                        }, scrollData.speed, scrollData.easing, function() {
                            $(this).hide()
                        });
                        $(nowScroll).css({
                            'z-index': 1,
                            'opacity': scrollData.startAlpha
                        }).show().animate({
                            'opacity': scrollData.endAlpha
                        }, scrollData.speed, scrollData.easing).find(scrollData.alphaObj).each(function(index, element) {
                            var nowObj = $(this).css({
                                    'position': 'absolute'
                                }),
                                nowTypeX = nowObj.attr(scrollData.attrTypeX),
                                nowTypeY = nowObj.attr(scrollData.attrTypeY),
                                xStyle = nowTypeX == 'right' ? 'right' : 'left',
                                yStyle = nowTypeY == 'bottom' ? 'bottom' : 'top',
                                xValue = nowObj.attr(scrollData.attrStartX) ? parseInt(nowObj.attr(scrollData.attrStartX)) : 0,
                                yValue = nowObj.attr(scrollData.attrStartY) ? parseInt(nowObj.attr(scrollData.attrStartY)) : 0,
                                nowAlpha = nowObj.attr(scrollData.attrStartAlpha) ? parseFloat(nowObj.attr(scrollData.attrStartAlpha)) : scrollData.startAlpha,
                                nowRotate = nowObj.attr(scrollData.attrStartRotate) ? parseInt(nowObj.attr(scrollData.attrStartRotate)) : 0,
                                nowScale = nowObj.attr(scrollData.attrStartScale) ? This.getSplitValue(nowObj.attr(scrollData.attrStartScale)) : null,
                                nowCss = nowObj.attr(scrollData.arrtStartCss) ? This.getSplitCss(nowObj.attr(scrollData.arrtStartCss)) : '',
                                transRotate = nowScale === null ? 1 : 0,
                                attrSpeed = scrollData.speed,
                                setStyle = {
                                    'opacity': nowAlpha,
                                    'margin-left': nowTypeX == 'center' ? -$(nowObj).outerWidth() / 2 + xValue + 'px' : '0px',
                                    'margin-top': nowTypeY == 'center' ? -$(nowObj).outerHeight() / 2 + yValue + 'px' : '0px'
                                };
                            setStyle['transition'] = '';
                            setStyle['transform'] = transRotate ? 'rotate(' + nowRotate + 'deg)' : 'scale(' + nowScale + ')';
                            setStyle[xStyle] = nowTypeX == 'center' || nowTypeX == 'middle' ? '50%' : xValue + 'px';
                            setStyle[yStyle] = nowTypeY == 'center' || nowTypeY == 'middle' ? '50%' : yValue + 'px';
                            setStyle = $.extend(setStyle, nowCss);
                            nowObj.css(setStyle);
                            setTimeout(function() {
                                xValue = nowObj.attr(scrollData.attrEndX) ? parseInt(nowObj.attr(scrollData.attrEndX)) : xValue;
                                yValue = nowObj.attr(scrollData.attrEndY) ? parseInt(nowObj.attr(scrollData.attrEndY)) : yValue;
                                nowAlpha = nowObj.attr(scrollData.attrEndAlpha) ? parseFloat(nowObj.attr(scrollData.attrEndAlpha)) : scrollData.endAlpha;
                                nowRotate = nowObj.attr(scrollData.attrEndRotate) ? parseFloat(nowObj.attr(scrollData.attrEndRotate)) : 0;
                                nowScale = nowObj.attr(scrollData.attrEndScale) ? This.getSplitValue(nowObj.attr(scrollData.attrEndScale)) : '1,1';
                                nowCss = nowObj.attr(scrollData.arrtEndCss) ? This.getSplitCss(nowObj.attr(scrollData.arrtEndCss)) : '';
                                attrSpeed = nowObj.attr(scrollData.attrSpeed) ? parseInt(nowObj.attr(scrollData.attrSpeed)) : attrSpeed;
                                setStyle['opacity'] = nowAlpha;
                                setStyle['margin-left'] = nowTypeX == 'center' ? -$(nowObj).outerWidth() / 2 + xValue + 'px' : '0px';
                                setStyle['margin-top'] = nowTypeY == 'center' ? -$(nowObj).outerHeight() / 2 + xValue + 'px' : '0px';
                                setStyle['transform'] = transRotate ? 'rotate(' + nowRotate + 'deg)' : 'scale(' + nowScale + ')';
                                setStyle[xStyle] = nowTypeX == 'center' || nowTypeX == 'middle' ? '50%' : xValue + 'px';
                                setStyle[yStyle] = nowTypeY == 'center' || nowTypeY == 'middle' ? '50%' : yValue + 'px';
                                setStyle = $.extend(setStyle, nowCss);
                                if (This.supportCss3()) {
                                    setStyle['transition'] = 'all ' + attrSpeed / 1000 + 's ease-out 0s';
                                    nowObj.css(setStyle)
                                } else {
                                    nowObj.animate(setStyle, attrSpeed, scrollData.easing)
                                }
                            }, parseInt(nowObj.attr(scrollData.attrTime) ? nowObj.attr(scrollData.attrTime) : 0))
                        });
                        setPage();
                        scrollData.scrollNow = nowScroll;
                        scrollData.scrollListen = setTimeout(function() {
                            scrollToNum(scrollData.scrollNum + 1)
                        }, scrollData.timeout);
                        $.isFunction(scrollData.fnHandler) && scrollData.fnHandler(scrollData.nowScroll, scrollData.scrollListen, scrollData)
                    })
                }
            };
            var setPage = function() {
                if ($(scrollData.parentObj).find(scrollData.pageObj).length > 0) {
                    $(scrollData.parentObj).find(scrollData.pageObj).find('a').removeClass('current');
                    $(scrollData.parentObj).find(scrollData.pageObj).find('a').eq(scrollData.scrollNum).addClass('current')
                }
            };
            This.addTouchEvevt({
                'moveLeft': function(moveX, moveObj) {
                    scrollToNum(scrollData.scrollNum + 1)
                },
                'moveRight': function(moveX, moveObj) {
                    scrollToNum(scrollData.scrollNum - 1)
                }
            }, scrollData.parentObj);
            $(scrollData.parentObj).find('a,input,button').bind('click.alphaBanner touchstart.alphaBanner touchmove.alphaBanner touchend.alphaBanner', function(event) {
                var _evt = This.getEvent();
                _evt && _evt.stopEvent()
            });
            if ($(scrollData.parentObj).find(scrollData.pageObj).length > 0) {
                for (var i = 0; i <= scrollData.scrollLen; i++) {
                    (function(scrolli) {
                        var addhtml = $(scrollData.scrollObj).eq(scrolli).attr('rel'),
                            addTitle = $(scrollData.scrollObj).eq(scrolli).attr('title');
                        addTitle = addTitle ? addTitle : '';
                        addhtml = addhtml ? '<table class="middle"><tr valign="top"><td><img src="' + addhtml + '" /></td></tr></table>' : (scrolli + 1);
                        var addStr = scrolli == 0 ? '<a class="current">' + addhtml + '</a>' : '<a>' + addhtml + '</a>';
                        $(addStr).attr('title', (addTitle ? addTitle : '')).appendTo($(scrollData.parentObj).find(scrollData.pageObj)).click(function() {
                            scrollToNum(scrolli, true)
                        })
                    })(i)
                }
            }
            if ($(scrollData.parentObj).find(scrollData.pageLeft).length > 0) {
                $(scrollData.parentObj).find(scrollData.pageLeft).click(function() {
                    scrollToNum(scrollData.scrollNum - 1)
                })
            }
            if ($(scrollData.parentObj).find(scrollData.pageRight).length > 0) {
                $(scrollData.parentObj).find(scrollData.pageRight).click(function() {
                    scrollToNum(scrollData.scrollNum + 1)
                })
            }
            scrollToNum(0);
            return scrollData
        },
        bindCurrent: function(bindClass, clickFunc, mouseHover, currentClass) {
            var mouseHover = mouseHover ? 1 : 0,
                currentClass = currentClass ? currentClass : 'active';
            if (mouseHover) {
                $(bindClass).hover(function() {
                    $(bindClass).removeClass(currentClass);
                    $(this).addClass(currentClass);
                    if ($.isFunction(clickFunc)) {
                        clickFunc($(this)[0])
                    }
                })
            } else {
                $(bindClass).click(function() {
                    $(bindClass).removeClass(currentClass);
                    $(this).addClass(currentClass);
                    if ($.isFunction(clickFunc)) {
                        clickFunc($(this)[0])
                    }
                })
            }
            return $(bindClass).hasClass(currentClass).length > 0 ? $(bindClass).hasClass(currentClass) : $(bindClass).eq(0)
        },
        getScrollTop: function(windowObj) {
            if (!windowObj) {
                return this.browser.isIE || this.browser.isFirefox ? window.document.documentElement.scrollTop : window.document.body.scrollTop
            }
            var windowObj = windowObj ? $(windowObj)[0] : window;
            if (windowObj == window) {
                return this.browser.isIE || this.browser.isFirefox ? windowObj.document.documentElement.scrollTop : windowObj.document.body.scrollTop
            } else {
                return windowObj.scrollTop
            }
        },
        getScrollLeft: function(windowObj) {
            if (!windowObj) {
                return this.browser.isIE || this.browser.isFirefox ? window.document.documentElement.scrollLeft : window.document.body.scrollLeft
            }
            var windowObj = windowObj ? $(windowObj)[0] : window;
            if (windowObj == window) {
                return this.browser.isIE ? windowObj.document.documentElement.scrollLeft : windowObj.document.body.scrollLeft
            } else {
                return windowObj.scrollLeft
            }
        },
        getScrollHeight: function(windowObj) {
            if (!windowObj) {
                return this.browser.isIE || this.browser.isFirefox ? window.document.documentElement.scrollHeight : window.document.body.scrollHeight
            }
            var windowObj = windowObj ? $(windowObj)[0] : window;
            if (windowObj == window) {
                return this.browser.isIE ? windowObj.document.documentElement.scrollHeight : windowObj.document.body.scrollHeight
            } else {
                return windowObj.scrollHeight
            }
        },
        scrollTo: function(byObj, overFunc, position, limitHeight) {
            var byObj = byObj ? byObj : document.body,
                goPosition = 0,
                limitHeight = limitHeight ? parseInt(limitHeight) : 0;
            switch (position) {
                case 'bottom':
                    goPosition = $(byObj).offset().top + $(byObj).height();
                    break;
                case 'middle':
                    goPosition = $(byObj).offset().top + ($(byObj).height() - $(document.body).height()) / 2;
                case 'top':
                default:
                    goPosition = $(byObj).offset().top;
                    break
            }
            if (this.browser.isIE || this.browser.isFirefox) {
                console.debug(goPosition + limitHeight);
                this.toAnimate('document.documentElement.scrollTop', goPosition + limitHeight, '', '', overFunc)
            } else {
                console.debug(goPosition + limitHeight);
                this.toAnimate('document.body.scrollTop', goPosition + limitHeight, '', '', overFunc)
            }
        },
        scrollToBottom: function(byObj, overFunc, limitHeight) {
            this.scrollTo(byObj, overFunc, 'bottom', limitHeight)
        },
        scrollToMiddle: function(byObj, overFunc, limitHeight) {
            this.scrollTo(byObj, overFunc, 'middle', limitHeight)
        },
        flicker: function(obj, cssObj, timeLimit) {
            if ($(obj).length > 0 && cssObj) {
                var count = 1,
                    timeLimit = timeLimit ? parseInt(timeLimit) : 400;
                var flicker = function() {
                    if (count++ % 2 == 0) {
                        $(obj).addClass(cssObj)
                    } else {
                        $(obj).removeClass(cssObj)
                    }
                }
                setInterval(flicker, timeLimit)
            }
        },
        bindTabs : function( tabs, tabFunc, hoverChange, attrAction, attrDisable, current ){

            var tabs = $(tabs), hoverChange = hoverChange ? 1 : 0,
                attrAction = attrAction ? attrAction : 'data-action',
                attrDisable = attrDisable ? attrDisable : 'data-disable',
                current = current ? current : 'active',
                firstTab = null, actionIds = [], disableIds = [];

            if( tabs.length < 1 ){ return false; }

            if( tabs.filter('.'+current).length < 1 ){ tabs.filter(':eq(0)').addClass(current); }

            firstTab = ( tabs.filter('.'+current).length > 0 ? tabs.filter('.'+current+':eq(0)') : tabs.filter(':eq(0)') );

            tabs.each(function(){
                $(this).attr(attrAction) && actionIds.push($(this).attr(attrAction));
                $(this).attr(attrDisable) && disableIds.push($(this).attr(attrDisable));
            });

            actionIds = actionIds.join(',');
            disableIds = disableIds.join(',');

            var tabFunction = function( tabCurrent ){

                if( tabCurrent == null || typeof tabCurrent == 'undefined' ){
                    tabCurrent = firstTab;
                }else if( $.isNumeric(tabCurrent) ){
                    tabCurrent = tabs.filter(':eq('+tabCurrent+')');
                }

                var actionCurrent = $(tabCurrent).attr(attrAction), disableCurrent = $(tabCurrent).attr(attrDisable);

                $(tabs).removeClass(current);
                $(tabCurrent).addClass(current);

                actionIds && $(actionIds).hide();
                actionCurrent && $(actionCurrent).show();

                disableIds && $(disableIds).find('input,textarea,select').attr('readonly','readonly').addClass('readonly');
                disableIds && $(disableIds).find('input:button,button,.ibtn').attr('disabled','disabled').addClass('disabled');
                disableCurrent && $(disableCurrent).find('input,textarea,select').attr('readonly',false).removeClass('readonly');
                disableCurrent && $(disableCurrent).find('input:button,button,.ibtn').attr('disabled',false).removeClass('disabled');

                $.isFunction(tabFunc) && tabFunc(tabCurrent,actionCurrent,disableCurrent);

            };

            hoverChange ? $(tabs).hover(function(){ tabFunction(this); }) : $(tabs).click(function(){ tabFunction(this); });

            if( actionIds || disableIds ){

                actionIds && $(actionIds).hide();
                $(firstTab.attr(attrAction)).show();

                disableIds && $(disableIds).find('input,textarea,select').attr('readonly','readonly').addClass('readonly');
                disableIds && $(disableIds).find('input:button,button,.ibtn').attr('disabled','disabled').addClass('disabled');
                $(firstTab.attr(attrDisable)).find('input,textarea,select').attr('readonly',false).removeClass('readonly');
                $(firstTab.attr(attrDisable)).find('input:button,button,.ibtn').attr('disabled',false).removeClass('disabled');

            }

            return tabFunction;

        },
        bindFilterSearch: function(filterObj, setting, changeHandler) {
            var setting = $.extend({
                    'select': '.filter-select',
                    'base': '.filter-base',
                    'checked': '.filter-checked',
                    'clean': '.filter-clean',
                    'activeClass': 'active',
                    'baseClass': ''
                }, setting || {}),
                filterObj = $(filterObj);
            if (filterObj.length > 0) {
                var filterSelect = filterObj.find(setting.select),
                     filterChecked = filterObj.find(setting.checked),
                    filterClean = filterObj.find(setting.clean),
                    changeHandler = changeHandler && $.isFunction(changeHandler) ? changeHandler : null,
                    initChecked = function() {
                        var datakeys = [];
                        filterChecked.empty();
                        filterSelect.find('a[data-key]').each(function() {
                            var datakey = $(this).attr('data-key');
                            if ($(this).hasClass(setting.activeClass) && !$(this).hasClass(setting.baseClass) &&
                                filterChecked.find('a[data-key=' + datakey + ']').length < 1) {
                                filterChecked.append('<a data-key="' + datakey + '">' + $(this).html() + '</a>');
                                datakeys.push(datakey)
                            } /*else {
                                filterChecked.find('a[data-key=' + datakey + ']').remove()
                            }*/
                        });
                        changeHandler && changeHandler(datakeys)
                    };
                setting.baseClass = setting.base.replace(/^[\.#]/, '');
                filterSelect.find('a[data-key]').click(function() {
                    var datakey = $(this).attr('data-key'),
                        parents = $(this).parents(setting.select);
                    if (datakey) {
                        $(this).hasClass(setting.activeClass) ? $(this).removeClass(setting.activeClass) : $(this).addClass(setting.activeClass);
                        initChecked()
                    }
                });
                filterChecked.on('click', 'a[data-key]', function() {
                    var datakey = $(this).attr('data-key'),
                        dataobj = filterSelect.find('a[data-key=' + datakey + ']');
                    dataobj.removeClass(setting.activeClass);
                    initChecked()
                });
                filterChecked.on('click', 'a[data-keyword]', function() {
                    $(this).remove();
                });
                filterClean.on('click', function() {
                    filterSelect.find('a[data-key]').removeClass(setting.activeClass);
                    initChecked()
                });
                initChecked()
            }
        },
        getCheckboxValue: function(checkboxs, reString) {
            var Values = [];
            $(checkboxs + "," + checkboxs + " input[type=checkbox]").each(function() {
                if ($(this).attr('checked') == 'checked' || $(this).attr('checked') == true) {
                    Values.push($(this).val())
                }
            });
            return reString ? Values.join(',') : Values
        },
        randKeyJson: {},
        randKey: function() {
            var This = this,
                id = Math.round(Math.random() * 1000000);
            id = This.randKeyJson[id] ? This.randKey() : id;
            This.randKeyJson[id] = 1;
            return id
        },
        dialogObjs: {},
        dialogBgs: {},
        dialogFunctions: {},
        dialogResizeFunctions: {},
        dialogCloseRemoves: {},
        dialogCloseListens: {},
        dialogAnimate: {},
        dialogKey: null,
        dialogClickHandler: {},
        dialogEscHandler: {},
        dialogEnterHandler: {},
        dialogIndex: 0,
        dialog: function(setting, dialogKey) {
            $('html,body').css({
                'position': 'relative',
                'width': '100%',
                'height': '100%'
            });
            var defaultSetting = {
                    'obj': null,
                    'byObj': null,
                    'append': false,
                    'remove': false,
                    'position': '',
                    'zindex': 8888,
                    'bgColor': true,
                    'bgOpacity': 0.45,
                    'animate': false,
                    'resize': true,
                    'isFloat': false,
                    'blurClose': false,
                    'clickClose': false,
                    'bodyLocking': false,
                    'bgClass': 'dialogBackground',
                    'closeBtnClass': 'dialogBtnClose',
                    'headerClass': 'dialogHeader',
                    'useAbsolute': false,
                    'absolute': 'fixed',
                    'cssData': {},
                    'fnHandler': null,
                    'resizeHandler': null,
                    'closeHandler': null,
                    'enterHandler': null,
                    'escHandler': null
                },
                This = this,
                Body = $(document.body);
            if (typeof setting == 'string') {
                setting = {
                    'obj': setting
                }
            }
            if ($.isPlainObject(setting)) {
                setting = $.extend(defaultSetting, setting)
            } else {
                setting = $.extend(defaultSetting, {
                    'obj': setting
                })
            }
            setting.blurClose = setting.clickClose ? setting.clickClose : setting.blurClose;
            setting.useAbsolute = This.browser.isIE6 || setting.isFloat || setting.absolute == 'absolute' ? true : setting.useAbsolute;
            setting.absolute = setting.useAbsolute ? 'absolute' : 'fixed';
            if (!setting.obj) {
                return false
            }
            setting.zindex += This.dialogIndex;
            This.dialogIndex += 10;
            if (dialogKey && This.dialogObjs[dialogKey]) {
                var closeObj = null;
                This.dialogClose(dialogKey, false, function() {
                    closeObj = This.dialog(setting, dialogKey)
                });
                return closeObj
            }
            if (setting.append || (typeof setting.obj == 'string' && setting.obj.indexOf('#') != 0)) {
                setting.obj = $('<div class="dialogAbsolute"><div class="dialogRelative">'+setting.obj+'</div></div>').css({
                    'position': setting.absolute,
                    'display': 'none',
                    'z-index': setting.zindex + 2,
                    'max-width': '100%',
                    'max-height': '100%'
                }).appendTo(Body);
                setting.remove = true
            }
            if ($(setting.obj).length < 1) {
                return false
            }
            var _dialogEvt = This.getEvent(),
                bgColor = setting.bgColor,
                fllowMouse = setting.byObj == 'fllow' ? 1 : 0,
                byMouse = setting.byObj == 'mouse' ? 1 : 0,
                Obj = $(setting.obj),
                byObj = fllowMouse || byMouse ? null : $(setting.byObj),
                cssData = $.extend({
                    'position': setting.absolute,
                    'z-index': setting.zindex + 1
                }, setting.cssData),
                tempFnHandler = null,
                dialogFunction = null,
                resizeFunction = null,
                dialogKey = dialogKey ? dialogKey : 'dialog' + This.randKey();
            if (byObj && byObj.length > 0) {
                dialogFunction = function(isResize) {
                    var left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2),
                        top = byObj.offset().top + parseInt(byObj.outerHeight() * 0.4 - Obj.outerHeight() / 2);
                    setting.position = setting.position ? setting.position : 'bottom';
                    switch (setting.position) {
                        case 'outtop':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'outleft':
                            left = byObj.offset().left - Obj.outerWidth();
                            top = byObj.offset().top + parseInt((byObj.outerHeight() - Obj.outerHeight()) / 2);
                            break;
                        case 'outbottom':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'outright':
                            left = byObj.offset().left + byObj.outerWidth();
                            top = byObj.offset().top + parseInt((byObj.outerHeight() - Obj.outerHeight()) / 2);
                            break;
                        case 'top':
                        case 'topcenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top;
                            break;
                        case 'topleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top;
                            break;
                        case 'topright':
                            left = byObj.offset().left + byObj.outerWidth() - Obj.outerWidth();
                            top = byObj.offset().top;
                            break;
                        case 'outtopcenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'outtopleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'outtopright':
                            left = byObj.offset().left + byObj.outerWidth() - Obj.outerWidth();
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'bottom':
                        case 'bottomcenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'bottomleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'bottomright':
                            left = byObj.offset().left + parseInt(byObj.outerWidth()) - Obj.outerWidth();
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'middle':
                        case 'middlecenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt((byObj.outerHeight() - Obj.outerHeight()) / 2);
                            break;
                        case 'middleleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top;
                            break;
                        case 'middleright':
                            left = byObj.offset().left + parseInt(byObj.outerWidth()) - parseInt(Obj.outerWidth());
                            top = byObj.offset().top;
                            break;
                        default:
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break
                    }
                    if (!setting.useAbsolute) {
                        top -= This.getScrollTop()
                    } else if (setting.isFloat) {
                        top += This.getScrollTop()
                    }
                    top = Math.max(top, 0);
                    if (setting.animate && !isResize) {
                        topStart = setting.animate === 'top' ? top - Obj.outerHeight() * 0.5 : top + Obj.outerHeight() * 0.5;
                        tempFnHandler = setting.fnHandler;
                        if (This.supportCss3()) {
                            $.extend(cssData, {
                                'left': left,
                                'top': topStart,
                                'opacity': 0,
                                'transform': 'scale(0.5,0.5)'
                            });
                            Obj.css(cssData).animate({
                                'top': top,
                                'opacity': 1
                            }, {
                                'step': function(now, fx) {
                                    $(this).css(fx.prop, now);
                                    if (fx.prop == 'opacity') {
                                        $(this).css('transform', 'scale(' + 0.5 * (1 + now) + ',' + 0.5 * (1 + now) + ')')
                                    }
                                },
                                'duration': 'fast',
                                'easing': 'swing',
                                'complete': function() {
                                    $.isFunction(tempFnHandler) && tempFnHandler(Obj, bgColor, dialogKey, dialogFunction)
                                }
                            }).show()
                        } else {
                            $.extend(cssData, {
                                'left': left,
                                'top': topStart,
                                'opacity': 0
                            });
                            Obj.css(cssData).animate({
                                'top': top,
                                'opacity': 1
                            }, 'fast', 'swing', function() {
                                $.isFunction(tempFnHandler) && tempFnHandler(Obj, bgColor, dialogKey, dialogFunction)
                            }).show()
                        }
                        setting.fnHandler = null
                    } else {
                        $.extend(cssData, {
                            'left': left,
                            'top': top,
                            'opacity': 1
                        });
                        Obj.css(cssData).show()
                    }
                }
            } else if (fllowMouse || byMouse) {
                dialogFunction = function() {
                    var leftValue = _dialogEvt.pageX,
                        topValue = _dialogEvt.pageY;
                    $.extend(cssData, {
                        'left': leftValue + 2,
                        'top': topValue + 2
                    });
                    Obj.css(cssData).show()
                }
            } else {
                dialogFunction = function(isResize) {
                    Obj.css(cssData).show(0, function() {
                        var scrollTop = setting.useAbsolute ? This.getScrollTop() : 0,
                            scrollLeft = setting.useAbsolute ? This.getScrollLeft() : 0,
                            topValue = null,
                            leftValue = null;
                        setting.position = setting.position ? setting.position : 'middle';
                        switch (setting.position) {
                            case 'top':
                            case 'topcenter':
                                topValue = 0;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'topleft':
                                topValue = 0;
                                leftValue = 0;
                                break;
                            case 'topright':
                                topValue = 0;
                                leftValue = $(Body).width() - Obj.outerWidth();
                                break;
                            case 'bottom':
                            case 'bottomcenter':
                                topValue = $(Body).height() - Obj.outerHeight();
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'bottomleft':
                                topValue = $(Body).height() - Obj.outerHeight();
                                leftValue = 0;
                                break;
                            case 'bottomright':
                                topValue = $(Body).height() - Obj.outerHeight();
                                leftValue = $(Body).width() - Obj.outerWidth();
                                break;
                            case 'middle':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2.4;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'middlecenter':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'middleleft':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = 0;
                                break;
                            case 'middleright':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = $(Body).width() - Obj.outerWidth();
                                break;
                            default:
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break
                        }
                        topValue += scrollTop;
                        leftValue += scrollLeft;
                        topValue = Math.max(topValue, 0);
                        leftValue = Math.max(leftValue, 0);
                        if (setting.animate && !isResize) {
                            topStart = setting.animate === 'top' ? topValue - Obj.outerHeight() * 0.5 : topValue + Obj.outerHeight() * 0.5;
                            topStart += scrollTop;
                            tempFnHandler = setting.fnHandler;
                            Obj.css({
                                'top': topStart,
                                'left': leftValue,
                                'opacity': 0,
                                'transform': 'scale(0.5,0.5)'
                            }).animate({
                                'top': topValue,
                                'opacity': 1
                            }, {
                                'step': function(now, fx) {
                                    $(this).css(fx.prop, now);
                                    if (fx.prop == 'opacity') {
                                        $(this).css('transform', 'scale(' + 0.5 * (1 + now) + ',' + 0.5 * (1 + now) + ')')
                                    }
                                },
                                'duration': 'fast',
                                'easing': 'swing',
                                'complete': function() {
                                    $.isFunction(tempFnHandler) && tempFnHandler(Obj, bgColor, dialogKey, dialogFunction)
                                }
                            });
                            setting.fnHandler = null
                        } else {
                            Obj.css({
                                'top': topValue,
                                'left': leftValue,
                                'opacity': 1
                            })
                        }
                    })
                }
            }
            dialogFunction && dialogFunction();
            This.loadImgs(Obj, function() {
                dialogFunction(true)
            });
            if (setting.isFloat && This.bindFloat) {
                This.bindFloat(Obj)
            }
            Obj && !setting.clickClose && Obj.bind('click.' + dialogKey, function(event) {
                var _evt = This.getEvent();
                _evt && _evt.stopEvent()
            });
            if (bgColor) {
                var width = $(document).width(),
                    height = $(document).height();
                bgColor = $('<div></div>').addClass(setting.bgClass).css({
                    'position': setting.absolute,
                    'z-index': setting.zindex,
                    opacity: setting.bgOpacity,
                    'width': '100%',
                    'height': height,
                    'left': '0px',
                    'top': '0px'
                }).appendTo(Body)
            }
            Obj.find('.' + setting.closeBtnClass).css({
                'z-index': setting.zindex + 3,
                'cursor': 'pointer'
            }).bind('click.' + dialogKey, function(event) {
                var _evt = This.getEvent();
                _evt && _evt.stop();
                This.dialogClose(dialogKey, setting.remove)
            });
            if (fllowMouse) {
                This.bindMouseFllow(Obj)
            } else if (byMouse) {} else if (Obj.find('.' + setting.headerClass).length > 0) {
                This.bindNewDrag({
                    'dragObj': Obj,
                    'dragHandler': '.' + setting.headerClass
                })
            }
            var clickHandler = null,
                escHandler = null,
                enterHandler = null;
            if (setting.blurClose) {
                if (_dialogEvt && _dialogEvt.preventDefault) {
                    clickHandler = function(event) {
                        This.dialogClose(dialogKey, setting.remove)
                    }
                    $(document).bind('click.' + dialogKey, clickHandler);
                    bgColor && $(bgColor).bind('click.' + dialogKey, clickHandler)
                }
                escHandler = function(event) {
                    if (event.keyCode == 27) {
                        This.dialogClose(dialogKey, setting.remove);
                        setting.escHandler && setting.escHandler(Obj, bgColor, dialogKey);
                        This.getEvent().stopEvent()
                    }
                }
            } else {
                escHandler = function(event) {
                    if (event.keyCode == 27) {
                        setting.escHandler && setting.escHandler(Obj, bgColor, dialogKey);
                        This.getEvent().stopEvent()
                    }
                }
            }
            $(document).bind('keydown.' + dialogKey, escHandler);
            $(window).focus();
            if (setting.bodyLocking) {}
            if (setting.enterHandler && $.isFunction(setting.enterHandler)) {
                enterHandler = function(event) {
                    if (event.keyCode == 13) {
                        setting.enterHandler(Obj, bgColor, dialogKey);
                        This.getEvent().stop()
                    }
                }
                $(Obj).find('input,textarea').bind('keydown.' + dialogKey, function(event) {
                    var _evt = This.getEvent();
                    _evt && _evt.stopEvent()
                });
                $(document).bind('keydown.' + dialogKey, enterHandler);
                $(window).focus()
            }
            resizeFunction = function() {
                if (setting.resize) {
                    dialogFunction && dialogFunction(true)
                }
                bgColor && bgColor.css({
                    'width': $(document).width(),
                    'height': $(document).height()
                });
                setting.resizeHandler && setting.resizeHandler(Obj, bgColor, dialogKey)
            }
            $(window).bind('scroll.' + dialogKey, resizeFunction);
            $(window).bind('resize.' + dialogKey, resizeFunction).resize();
            !tempFnHandler && $.isFunction(setting.fnHandler) && setting.fnHandler(Obj, bgColor, dialogKey, dialogFunction);
            _dialogEvt && _dialogEvt.stop();
            This.dialogKey = dialogKey;
            This.dialogObjs[dialogKey] = Obj;
            This.dialogBgs[dialogKey] = bgColor;
            This.dialogFunctions[dialogKey] = dialogFunction;
            This.dialogResizeFunctions[dialogKey] = resizeFunction;
            This.dialogCloseRemoves[dialogKey] = setting.remove;
            This.dialogCloseListens[dialogKey] = setting.closeHandler;
            This.dialogAnimate[dialogKey] = setting.animate;
            This.dialogClickHandler[dialogKey] = clickHandler;
            This.dialogEscHandler[dialogKey] = escHandler;
            This.dialogEnterHandler[dialogKey] = enterHandler;
            return Obj
        },
        dialogReset: function(dialogKey) {
            this.dialogFunctions[dialogKey] && this.dialogFunctions[dialogKey](true)
        },
        dialogGetObj: function(dialogKey) {
            return dialogKey ? this.dialogObjs[dialogKey] : this.dialogObjs[dialogKey]
        },
        dialogUnbind: function(dialogKey) {
            var This = this;
            This.dialogFunctions[dialogKey] && $(window).unbind('resize.' + dialogKey, This.dialogFunctions[dialogKey]);
            This.dialogResizeFunctions[dialogKey] && $(window).unbind('scroll.' + dialogKey, This.dialogResizeFunctions[dialogKey]) && $(window).unbind('resize.' + dialogKey, This.dialogResizeFunctions[dialogKey]);
            This.dialogClickHandler[dialogKey] && $(document).unbind('click.' + dialogKey, This.dialogClickHandler[dialogKey]);
            This.dialogEscHandler[dialogKey] && $(document).unbind('keydown.' + dialogKey, This.dialogEscHandler[dialogKey]);
            This.dialogEnterHandler[dialogKey] && $(document).unbind('keydown.' + dialogKey, This.dialogEnterHandler[dialogKey])
        },
        dialogClose: function(dialogKey, remove, fnHandler) {
            var This = this,
                remove = remove ? true : false,
                fnHandler = fnHandler ? fnHandler : null;
            /*$(document.body).css('overflow-y', 'auto');*/
            if (!this.dialogObjs) {
                return false
            }
            if (dialogKey && this.dialogObjs.hasOwnProperty(dialogKey) && this.dialogObjs[dialogKey]) {
                var ikey = dialogKey,
                    iObj = This.dialogObjs[ikey],
                    iBg = This.dialogBgs[ikey];
                This.dialogUnbind(ikey);
                This.dialogObjs[ikey] = null;
                $(document).unbind('click.' + dialogKey);
                if (This.dialogAnimate[ikey]) {
                    $(iObj).animate({
                        'top': $(iObj).offset().top - This.getScrollTop() - $(iObj).outerHeight() * 0.5,
                        'opacity': 0
                    }, 'fast', 'linear', function() {
                        if (remove || This.dialogCloseRemoves[ikey]) {
                            $(iObj).remove();
                            $(iBg).remove()
                        } else {
                            $(iObj).hide();
                            $(iBg).remove()
                        }
                        if ($.isFunction(This.dialogCloseListens[ikey])) {
                            This.dialogCloseListens[ikey](iObj, iBg, ikey)
                        }
                        if ($.isFunction(fnHandler)) {
                            fnHandler(iObj, iBg, ikey)
                        }
                    })
                } else {
                    if (remove || This.dialogCloseRemoves[ikey]) {
                        $(iObj).remove();
                        $(iBg).remove()
                    } else {
                        $(iObj).hide();
                        $(iBg).remove()
                    }
                    if ($.isFunction(This.dialogCloseListens[ikey])) {
                        This.dialogCloseListens[ikey](iObj, iBg, ikey)
                    }
                    if ($.isFunction(fnHandler)) {
                        fnHandler(iObj, iBg, ikey)
                    }
                }
            } else if (!dialogKey) {
                for (ikey in this.dialogObjs) {
                    if (!this.dialogObjs[ikey]) {
                        continue
                    }
                    var iObj = This.dialogObjs[ikey],
                        iBg = This.dialogBgs[ikey];
                    This.dialogUnbind(ikey);
                    This.dialogObjs[ikey] = null;
                    $(document).unbind('click.' + ikey);
                    if (This.dialogAnimate[ikey]) {
                        $(iObj).animate({
                            'top': $(iObj).offset().top - This.getScrollTop() - $(iObj).outerHeight() * 0.5,
                            'opacity': 0
                        }, 'fast', 'linear', function() {
                            if (remove || This.dialogCloseRemoves[ikey]) {
                                $(iObj).remove();
                                $(iBg).remove()
                            } else {
                                $(iObj).hide();
                                $(iBg).remove()
                            }
                            if ($.isFunction(This.dialogCloseListens[ikey])) {
                                This.dialogCloseListens[ikey](iObj, iBg, ikey)
                            }
                            if ($.isFunction(fnHandler)) {
                                fnHandler(iObj, iBg, ikey)
                            }
                        })
                    } else {
                        if (remove || This.dialogCloseRemoves[ikey]) {
                            $(iObj).remove();
                            $(iBg).remove()
                        } else {
                            $(iObj).hide();
                            $(iBg).remove()
                        }
                        if ($.isFunction(This.dialogCloseListens[ikey])) {
                            This.dialogCloseListens[ikey](iObj, iBg, ikey)
                        }
                        if ($.isFunction(fnHandler)) {
                            fnHandler(iObj, iBg, ikey)
                        }
                    }
                }
                this.dialogObjs = {}
            }
        },

        //é¦ã¥åç»±ç±ç¬éç°èéçå½ç»?é?æ©å§æéæ¯æ£
        pop : function( content, byObj, key, style, popSetting, outTime ){

            var This = this,
                content = content && typeof content == 'string' ?
                    ( content.indexOf('#') == 0 ? $(content).prop('outerHTML') : content.replace(/\\n|\n/g,'<br/>') ) :
                    ( content && $.isPlainObject(content) ? $(content).prop('outerHTML') : content ),
                style = style ? style : 'Alert',
                popKey = key ? 'pop'+style+key : 'pop'+style, outTime = outTime ? parseInt(outTime) : ( outTime === null ? null : 800 ),
                popSetting = $.isPlainObject(popSetting) ? popSetting : {};

            This.dialogClose(popKey,true); //ç»å©æ«

            var popObj = null;

            if( content ){

                if( byObj ){ //&& !$(byObj).is(':hidden')

                    var diologStr = '<div class="pop'+style+'"><div class="popArrow'+style+'"></div>'+content+'</div>';

                    popObj = This.dialog( $.extend({
                        'obj':diologStr,'byObj':byObj, 'position':'bottomleft', 'resize':true,
                        'z-index':666, 'animate':false, 'fnHandler':function( obj, bg, key ){
                            outTime && setTimeout( function(){ $(obj).fadeOut(function(){ obj.remove(); }); }, outTime );
                    }},popSetting), popKey );

                }else{

                    popObj = this.dialog( $.extend(
                        {'obj':'<div class="popTop'+style+'">'+content+'</div>','position':'topcenter','resize':true,
                            'z-index':666,'animate':true,'fnHandler':function( obj, bg, key ){
                            outTime && setTimeout( function(){ $(obj).fadeOut(function(){ obj.remove(); }); }, outTime );
                    }},popSetting), 'popTop' );

                }

            }

            return popObj;

        },

        /* å¯®ç°å­æ¶â¬æ¶îâçãî */
        alertKey : null,
        alertListen : null,
        alertListenOk : null,
        alertListenCancel : null,

        alert : function( content, ok, cancel, icon, title, popSetting, style, time, noLock ){
            return this.alertWindow( content, ok, cancel, icon, title, popSetting, style, time, (typeof noLock == 'undefined' ? false : noLock) );
        },

        alertBlur : function( content, ok, cancel, icon, title, popSetting, style, time, noLock ){
            return this.alertWindow(content, ok, cancel, icon, title, popSetting, style, time, (typeof noLock == 'undefined' ? true : noLock) );
        },

        alertWindow : function( content, ok, cancel, icon, title, popSetting, style, time, noLock ){

            var This = this, okStr = 'ç¡®è®¤', cancelStr = 'åæ¶',
                alertStyle = style ? 'alertStyle'+style : 'alertStyle',
                noLock = noLock ? 1 : 0,
                icon = icon? '<div class="popIcon">'+icon+'</div>' : '',
                content = content && typeof content == 'string' ?
                    ( content.indexOf('#') == 0 ? $(content).prop('outerHTML') : content.replace(/\\n|\n/g,'<br/>') ) :
                    ( content && $.isPlainObject(content) ? $(content).prop('outerHTML') : content ),
                popSetting = $.isPlainObject(popSetting) ? popSetting : {},
                alertKey = 'alert';

            content = icon+content;

            var diologStr = '<div class="'+alertStyle+'">'+
                '<div class="popContent popContentAlert" style="min-width:230px;"><div class="popHeader">'+(title?title:'æç¤ºä¿¡æ¯')+'</div>'+
                '<div class="popMargin">'+(content?content:'')+'</div>';

            if( ok !== null ){
                if( $.isPlainObject(ok) ){
                    okStr = ok.str ? ok.str : okStr;
                    ok = ok.fn ? ok.fn : false;
                }else if( ok && !$.isFunction(ok) ){
                    okStr = ok.toString();
                    ok = false;
                }
            }

            if( cancel !== null ){
                if( $.isPlainObject(cancel) ){
                    cancelStr = cancel.str ? cancel.str : cancelStr;
                    cancel = cancel.fn ? cancel.fn : false;
                }else if( cancel && !$.isFunction(cancel) ){
                    cancelStr = cancel.toString();
                    cancel = false;
                }
            }

            if( ok !== null || cancel !== null ){

                diologStr += '<div class="dialogBtns">';

                if( ok !== null ){
                    diologStr	+= '<input class="ibtn ibtn-ok" type="button" value="'+okStr+'" onclick="mini.alertOk(\''+alertKey+'\');" />';
                }

                if( cancel !== null ){
                    diologStr	+= '<input class="ibtn ibtn-cancel" type="button" value="'+cancelStr+'" onclick="mini.alertCancel(\''+alertKey+'\');" />';
                }

                diologStr += '</div>';

            }

            diologStr += '</div></div>';

            This.alertListenOk = $.isFunction(ok) ? ok : null;
            This.alertListenCancel = $.isFunction(cancel) ? cancel : null;

            var alertObj = null;

            if( time && time >0 ){
                This.alertListen = setTimeout(function(){
                    alertObj = This.dialog( $.extend({'obj':diologStr,'bgColor':true,'blurClose':noLock,'append':true,'enterHandler':function(){
                        This.alertOk(alertKey);
                    },'escHandler':function( reObj, rebgColor, repopKey ){
                        This.alertCancel(alertKey);
                    } } , popSetting), alertKey );
                },parseInt(time) );
            }else{
                alertObj = This.dialog( $.extend({'obj':diologStr,'bgColor':true,'blurClose':noLock,'append':true,'enterHandler':function(){
                    This.alertOk(alertKey);
                },'escHandler':function( reObj, rebgColor, repopKey ){
                    This.alertCancel(alertKey);
                } },popSetting), alertKey );
            }

            this.alertKey = alertKey;

            return alertObj;

        },

        alertOk : function(alertKey){
            var _evt = this.getEvent(), cBack = true;
            _evt && _evt.stopEvent();
            if( null != this.alertListenOk && $.isFunction(this.alertListenOk) ){ cBack = this.alertListenOk( this.popGetObj(alertKey) ); }
            ( typeof cBack == 'undefined' || cBack ) && this.alertClose();
        },

        alertCancel : function(alertKey){
            var _evt = this.getEvent(), cBack = true;
            _evt && _evt.stopEvent();
            if( null != this.alertListenCancel && $.isFunction(this.alertListenCancel) ){ cBack = this.alertListenCancel( this.popGetObj(alertKey) ); }
            ( typeof cBack == 'undefined' || cBack ) && this.alertClose();
        },

        alertClose : function(){
            if( null != this.alertListen  ){ clearTimeout(this.alertListen); this.alertListen = null; }
            if( null != this.alertKey ){ this.dialogClose(this.alertKey,true); this.alertKey = null; }
        },

        //å¼¹åºåäº«å±
        dialogShare : function( title, content, byobj ){

            var shareContent = '<div class="dialog-share">'+
                '<a><i class="fgsocial fgsocial-picasa"></i>å¾®å</a>'+
                '<a><i class="fgsocial fgsocial-picasa"></i>å¾®ä¿¡</a>'+
                '<a><i class="fgsocial fgsocial-picasa"></i>å¶ä»</a></div>';

            this.dialog({
                'obj' : shareContent,
                'byobj' : byobj, 'positon' : 'bottom', 'blurClose' : true,
                'fnHandler' : function( content ){
                    $(content).on('click','a',function(){
                        mini.dialogClose();
                        mini.alert('åäº«æå!');
                    });
                }
            });

        },

        //å¼¹åºæè¦å±
        dialogSummary : function( title, content ){
            console.log('666',window.screenTop);
            var summaryDialog = '<div class="dialog-summary"><span class="dialogBtnClose"></span>'+
                '<div class="dialog-summary-title">'+title+'</div>'+
                '<div class="dialog-summary-content">'+content+'</div></div>';

            this.dialog({
                'obj' : summaryDialog
            });

        },
        dialogB: function(setting, dialogKey) {
            $('html,body').css({
                'position': 'relative',
                'width': '100%',
                'height': '100%'
            });
            var defaultSetting = {
                    'obj': null,
                    'byObj': null,
                    'append': false,
                    'remove': false,
                    'position': '',
                    'zindex': 8888,
                    'bgColor': true,
                    'bgOpacity': 0.45,
                    'animate': false,
                    'resize': true,
                    'isFloat': false,
                    'blurClose': false,
                    'clickClose': false,
                    'bodyLocking': false,
                    'bgClass': 'dialogBackground',
                    'closeBtnClass': 'dialogBtnClose',
                    'headerClass': 'dialogHeader',
                    'useAbsolute': false,
                    'absolute': 'fixed',
                    'cssData': {},
                    'fnHandler': null,
                    'resizeHandler': null,
                    'closeHandler': null,
                    'enterHandler': null,
                    'escHandler': null
                },
                This = this,
                Body = $(document.body);
            if (typeof setting == 'string') {
                setting = {
                    'obj': setting
                }
            }
            if ($.isPlainObject(setting)) {
                setting = $.extend(defaultSetting, setting)
            } else {
                setting = $.extend(defaultSetting, {
                    'obj': setting
                })
            }
            setting.blurClose = setting.clickClose ? setting.clickClose : setting.blurClose;
            setting.useAbsolute = This.browser.isIE6 || setting.isFloat || setting.absolute == 'absolute' ? true : setting.useAbsolute;
            setting.absolute = setting.useAbsolute ? 'absolute' : 'fixed';
            if (!setting.obj) {
                return false
            }
            setting.zindex += This.dialogIndex;
            This.dialogIndex += 10;
            if (dialogKey && This.dialogObjs[dialogKey]) {
                var closeObj = null;
                This.dialogClose(dialogKey, false, function() {
                    closeObj = This.dialog(setting, dialogKey)
                });
                return closeObj
            }
            if (setting.append || (typeof setting.obj == 'string' && setting.obj.indexOf('#') != 0)) {
                setting.obj = $(setting.obj).css({
                    'position': setting.absolute,
                    'display': 'none',
                    'z-index': setting.zindex + 2,
                    'max-width': '100%',
                    'max-height': '100%'
                }).appendTo(Body);
                setting.remove = true
            }
            if ($(setting.obj).length < 1) {
                return false
            }
            var _dialogEvt = This.getEvent(),
                bgColor = setting.bgColor,
                fllowMouse = setting.byObj == 'fllow' ? 1 : 0,
                byMouse = setting.byObj == 'mouse' ? 1 : 0,
                Obj = $(setting.obj),
                byObj = fllowMouse || byMouse ? null : $(setting.byObj),
                cssData = $.extend({
                    'position': setting.absolute,
                    'z-index': setting.zindex + 1
                }, setting.cssData),
                tempFnHandler = null,
                dialogFunction = null,
                resizeFunction = null,
                dialogKey = dialogKey ? dialogKey : 'dialog' + This.randKey();
            if (byObj && byObj.length > 0) {
                dialogFunction = function(isResize) {
                    var left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2),
                        top = byObj.offset().top + parseInt(byObj.outerHeight() * 0.4 - Obj.outerHeight() / 2);
                    setting.position = setting.position ? setting.position : 'bottom';
                    switch (setting.position) {
                        case 'outtop':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'outleft':
                            left = byObj.offset().left - Obj.outerWidth();
                            top = byObj.offset().top + parseInt((byObj.outerHeight() - Obj.outerHeight()) / 2);
                            break;
                        case 'outbottom':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'outright':
                            left = byObj.offset().left + byObj.outerWidth();
                            top = byObj.offset().top + parseInt((byObj.outerHeight() - Obj.outerHeight()) / 2);
                            break;
                        case 'top':
                        case 'topcenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top;
                            break;
                        case 'topleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top;
                            break;
                        case 'topright':
                            left = byObj.offset().left + byObj.outerWidth() - Obj.outerWidth();
                            top = byObj.offset().top;
                            break;
                        case 'outtopcenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'outtopleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'outtopright':
                            left = byObj.offset().left + byObj.outerWidth() - Obj.outerWidth();
                            top = byObj.offset().top - Obj.outerHeight();
                            break;
                        case 'bottom':
                        case 'bottomcenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'bottomleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'bottomright':
                            left = byObj.offset().left + parseInt(byObj.outerWidth()) - Obj.outerWidth();
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break;
                        case 'middle':
                        case 'middlecenter':
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt((byObj.outerHeight() - Obj.outerHeight()) / 2);
                            break;
                        case 'middleleft':
                            left = byObj.offset().left;
                            top = byObj.offset().top;
                            break;
                        case 'middleright':
                            left = byObj.offset().left + parseInt(byObj.outerWidth()) - parseInt(Obj.outerWidth());
                            top = byObj.offset().top;
                            break;
                        default:
                            left = byObj.offset().left + parseInt((byObj.outerWidth() - Obj.outerWidth()) / 2);
                            top = byObj.offset().top + parseInt(byObj.outerHeight());
                            break
                    }
                    if (!setting.useAbsolute) {
                        top -= This.getScrollTop()
                    } else if (setting.isFloat) {
                        top += This.getScrollTop()
                    }
                    top = Math.max(top, 0);
                    if (setting.animate && !isResize) {
                        topStart = setting.animate === 'top' ? top - Obj.outerHeight() * 0.5 : top + Obj.outerHeight() * 0.5;
                        tempFnHandler = setting.fnHandler;
                        if (This.supportCss3()) {
                            $.extend(cssData, {
                                'left': left,
                                'top': topStart,
                                'opacity': 0,
                                'transform': 'scale(0.5,0.5)'
                            });
                            Obj.css(cssData).animate({
                                'top': top,
                                'opacity': 1
                            }, {
                                'step': function(now, fx) {
                                    $(this).css(fx.prop, now);
                                    if (fx.prop == 'opacity') {
                                        $(this).css('transform', 'scale(' + 0.5 * (1 + now) + ',' + 0.5 * (1 + now) + ')')
                                    }
                                },
                                'duration': 'fast',
                                'easing': 'swing',
                                'complete': function() {
                                    $.isFunction(tempFnHandler) && tempFnHandler(Obj, bgColor, dialogKey, dialogFunction)
                                }
                            }).show()
                        } else {
                            $.extend(cssData, {
                                'left': left,
                                'top': topStart,
                                'opacity': 0
                            });
                            Obj.css(cssData).animate({
                                'top': top,
                                'opacity': 1
                            }, 'fast', 'swing', function() {
                                $.isFunction(tempFnHandler) && tempFnHandler(Obj, bgColor, dialogKey, dialogFunction)
                            }).show()
                        }
                        setting.fnHandler = null
                    } else {
                        $.extend(cssData, {
                            'left': left,
                            'top': top,
                            'opacity': 1
                        });
                        Obj.css(cssData).show()
                    }
                }
            } else if (fllowMouse || byMouse) {
                dialogFunction = function() {
                    var leftValue = _dialogEvt.pageX,
                        topValue = _dialogEvt.pageY;
                    $.extend(cssData, {
                        'left': leftValue + 2,
                        'top': topValue + 2
                    });
                    Obj.css(cssData).show()
                }
            } else {
                dialogFunction = function(isResize) {
                    Obj.css(cssData).show(0, function() {
                        var scrollTop = setting.useAbsolute ? This.getScrollTop() : 0,
                            scrollLeft = setting.useAbsolute ? This.getScrollLeft() : 0,
                            topValue = null,
                            leftValue = null;
                        setting.position = setting.position ? setting.position : 'middle';
                        switch (setting.position) {
                            case 'top':
                            case 'topcenter':
                                topValue = 0;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'topleft':
                                topValue = 0;
                                leftValue = 0;
                                break;
                            case 'topright':
                                topValue = 0;
                                leftValue = $(Body).width() - Obj.outerWidth();
                                break;
                            case 'bottom':
                            case 'bottomcenter':
                                topValue = $(Body).height() - Obj.outerHeight();
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'bottomleft':
                                topValue = $(Body).height() - Obj.outerHeight();
                                leftValue = 0;
                                break;
                            case 'bottomright':
                                topValue = $(Body).height() - Obj.outerHeight();
                                leftValue = $(Body).width() - Obj.outerWidth();
                                break;
                            case 'middle':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2.4;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'middlecenter':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break;
                            case 'middleleft':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = 0;
                                break;
                            case 'middleright':
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = $(Body).width() - Obj.outerWidth();
                                break;
                            default:
                                topValue = ($(Body).height() - Obj.outerHeight()) / 2;
                                leftValue = ($(Body).width() - Obj.outerWidth()) / 2;
                                break
                        }
                        topValue += scrollTop;
                        leftValue += scrollLeft;
                        topValue = Math.max(topValue, 0);
                        leftValue = Math.max(leftValue, 0);
                        if (setting.animate && !isResize) {
                            topStart = setting.animate === 'top' ? topValue - Obj.outerHeight() * 0.5 : topValue + Obj.outerHeight() * 0.5;
                            topStart += scrollTop;
                            tempFnHandler = setting.fnHandler;
                            Obj.css({
                                'top': topStart,
                                'left': leftValue,
                                'opacity': 0,
                                'transform': 'scale(0.5,0.5)'
                            }).animate({
                                'top': topValue,
                                'opacity': 1
                            }, {
                                'step': function(now, fx) {
                                    $(this).css(fx.prop, now);
                                    if (fx.prop == 'opacity') {
                                        $(this).css('transform', 'scale(' + 0.5 * (1 + now) + ',' + 0.5 * (1 + now) + ')')
                                    }
                                },
                                'duration': 'fast',
                                'easing': 'swing',
                                'complete': function() {
                                    $.isFunction(tempFnHandler) && tempFnHandler(Obj, bgColor, dialogKey, dialogFunction)
                                }
                            });
                            setting.fnHandler = null
                        } else {
                            Obj.css({
                                'top': topValue,
                                'left': leftValue,
                                'opacity': 1
                            })
                        }
                    })
                }
            }
            dialogFunction && dialogFunction();
            This.loadImgs(Obj, function() {
                dialogFunction(true)
            });
            if (setting.isFloat && This.bindFloat) {
                This.bindFloat(Obj)
            }
            Obj && !setting.clickClose && Obj.bind('click.' + dialogKey, function(event) {
                var _evt = This.getEvent();
                _evt && _evt.stopEvent()
            });
            if (bgColor) {
                var width = $(document).width(),
                    height = $(document).height();
                bgColor = $('<div></div>').addClass(setting.bgClass).css({
                    'position': setting.absolute,
                    'z-index': setting.zindex,
                    opacity: setting.bgOpacity,
                    'width': '100%',
                    'height': height,
                    'left': '0px',
                    'top': '0px'
                }).appendTo(Body)
            }
            Obj.find('.' + setting.closeBtnClass).css({
                'z-index': setting.zindex + 3,
                'cursor': 'pointer'
            }).bind('click.' + dialogKey, function(event) {
                var _evt = This.getEvent();
                _evt && _evt.stop();
                This.dialogClose(dialogKey, setting.remove)
            });
            if (fllowMouse) {
                This.bindMouseFllow(Obj)
            } else if (byMouse) {} else if (Obj.find('.' + setting.headerClass).length > 0) {
                This.bindNewDrag({
                    'dragObj': Obj,
                    'dragHandler': '.' + setting.headerClass
                })
            }
            var clickHandler = null,
                escHandler = null,
                enterHandler = null;
            if (setting.blurClose) {
                if (_dialogEvt && _dialogEvt.preventDefault) {
                    clickHandler = function(event) {
                        This.dialogClose(dialogKey, setting.remove)
                    }
                    $(document).bind('click.' + dialogKey, clickHandler);
                    bgColor && $(bgColor).bind('click.' + dialogKey, clickHandler)
                }
                escHandler = function(event) {
                    if (event.keyCode == 27) {
                        This.dialogClose(dialogKey, setting.remove);
                        setting.escHandler && setting.escHandler(Obj, bgColor, dialogKey);
                        This.getEvent().stopEvent()
                    }
                }
            } else {
                escHandler = function(event) {
                    if (event.keyCode == 27) {
                        setting.escHandler && setting.escHandler(Obj, bgColor, dialogKey);
                        This.getEvent().stopEvent()
                    }
                }
            }
            $(document).bind('keydown.' + dialogKey, escHandler);
            $(window).focus();
            if (setting.bodyLocking) {}
            if (setting.enterHandler && $.isFunction(setting.enterHandler)) {
                enterHandler = function(event) {
                    if (event.keyCode == 13) {
                        setting.enterHandler(Obj, bgColor, dialogKey);
                        This.getEvent().stop()
                    }
                }
                $(Obj).find('input,textarea').bind('keydown.' + dialogKey, function(event) {
                    var _evt = This.getEvent();
                    _evt && _evt.stopEvent()
                });
                $(document).bind('keydown.' + dialogKey, enterHandler);
                $(window).focus()
            }
            resizeFunction = function() {
                if (setting.resize) {
                    dialogFunction && dialogFunction(true)
                }
                bgColor && bgColor.css({
                    'width': $(document).width(),
                    'height': $(document).height()
                });
                setting.resizeHandler && setting.resizeHandler(Obj, bgColor, dialogKey)
            }
            $(window).bind('scroll.' + dialogKey, resizeFunction);
            $(window).bind('resize.' + dialogKey, resizeFunction).resize();
            !tempFnHandler && $.isFunction(setting.fnHandler) && setting.fnHandler(Obj, bgColor, dialogKey, dialogFunction);
            _dialogEvt && _dialogEvt.stop();
            This.dialogKey = dialogKey;
            This.dialogObjs[dialogKey] = Obj;
            This.dialogBgs[dialogKey] = bgColor;
            This.dialogFunctions[dialogKey] = dialogFunction;
            This.dialogResizeFunctions[dialogKey] = resizeFunction;
            This.dialogCloseRemoves[dialogKey] = setting.remove;
            This.dialogCloseListens[dialogKey] = setting.closeHandler;
            This.dialogAnimate[dialogKey] = setting.animate;
            This.dialogClickHandler[dialogKey] = clickHandler;
            This.dialogEscHandler[dialogKey] = escHandler;
            This.dialogEnterHandler[dialogKey] = enterHandler;
            return Obj
        },
        dialogQuestion : function( title, content,browser){
            var summaryDialog = '';
            if(browser == "IE"){
                summaryDialog = '<iframe about="blank"></iframe><div class="dialogAbsolute"><div class="dialogRelative"><div class="dialog-summary"><span class="dialogBtnClose"></span>'+
                    '<div class="dialog-summary-title">'+title+'</div>'+
                    '<div class="dialog-summary-content">'+content+'</div></div></div></div>';
            }else{
                summaryDialog = '<div class="dialogAbsolute"><div class="dialogRelative"><div class="dialog-summary"><span class="dialogBtnClose"></span>'+
                    '<div class="dialog-summary-title">'+title+'</div>'+
                    '<div class="dialog-summary-content">'+content+'</div></div></div></div>';
            }
            this.dialogB({
                'obj' : summaryDialog
            });

        },

        //å¤æ­æµè§å¨ç±»å
        myBrowser: function () {
            var userAgent = navigator.userAgent; //åå¾æµè§å¨çuserAgentå­ç¬¦ä¸²
            var isOpera = userAgent.indexOf("Opera") > -1;
            if (isOpera) {
                return "Opera"
            }//å¤æ­æ¯å¦Operaæµè§å¨
            if (userAgent.indexOf("Firefox") > -1) {
                return "FF";
            } //å¤æ­æ¯å¦Firefoxæµè§å¨
            if (userAgent.indexOf("Chrome") > -1){
                return "Chrome";
            }
            if (userAgent.indexOf("Safari") > -1) {
                return "Safari";
            } //å¤æ­æ¯å¦Safariæµè§å¨
            if (userAgent.indexOf("compatible") > -1 && userAgent.indexOf("MSIE") > -1 && !isOpera) {
                return "IE";
            }//å¤æ­æ¯å¦IEæµè§å¨
            if(userAgent.indexOf("rv") > -1){
                return "IE";
            }
        }
    });
    window.mini = mini
})(jQuery);






//----------------------------------------------------------------------------------------
